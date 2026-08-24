"""
Unified AI Service Layer for Generative AI Client Management, Auto-Retry, and Token Cost Tracking.
Abstracts underlying LLM providers (Gemini, OpenAI) and provides robust exponential backoff.
"""

import os
import json
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
from src.core.logger import logger

from src.core.config_loader import load_system_settings
from src.core.cost_estimator import calculate_api_cost
from src.core.constants import DefaultPath, EntityIdPrefix, generate_entity_id
from src.core.db import create_api_call_log, AuditLogService, ApiCallLogCreate


class AIService:
    """
    Unified LLM Client Service.
    Handles API key discovery, rate-limiting retry backoff, structured output parsing,
    and automatic token cost estimation.
    """

    def __init__(self, settings_path: str = DefaultPath.SETTINGS):
        self.settings_path = settings_path
        self._client: Optional[Any] = None
        self._reload_config()

    def _reload_config(self):
        settings = load_system_settings(self.settings_path)
        ai_cfg = settings.get("ai_provider", {})
        self.active_provider = ai_cfg.get("active_provider", "gemini").lower()
        self.max_retries = int(ai_cfg.get("max_retries", 3))
        self.max_images_per_request = int(ai_cfg.get("max_images_per_request", 50))
        
        provider_cfg = ai_cfg.get(self.active_provider, {})
        self.default_model = provider_cfg.get("model_name")
        if not self.default_model:
            raise ValueError(f"Missing required 'model_name' for AI provider '{self.active_provider}' in {self.settings_path}")

        self.api_key_env = provider_cfg.get("api_key_env")
        if not self.api_key_env:
            raise ValueError(f"Missing required 'api_key_env' for AI provider '{self.active_provider}' in {self.settings_path}")

        self.api_key = os.getenv(self.api_key_env, "").strip()
        self._client = None  # Invalidate cached client on config reload

    def get_client(self):
        """Returns the active AI provider client instance (cached per config)."""
        if self._client is None:
            if not self.api_key:
                self._reload_config()

            if not self.api_key:
                raise ValueError(f"AI API key environment variable '{self.api_key_env}' is not set in environment or .env file.")

            if self.active_provider == "gemini":
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            else:
                raise NotImplementedError(f"AI Provider '{self.active_provider}' is not yet supported.")
        return self._client

    def extract_structured_json(
        self,
        prompt: str,
        images: List[Image.Image],
        response_schema: Optional[Dict[str, Any]] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.1,
        batch_id: Optional[str] = None,
        company_id: Optional[str] = None,
        chunk_index: int = 1,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Synchronously sends multimodal prompt + images to the configured LLM and returns parsed JSON.
        Includes built-in exponential backoff auto-retry and telemetry database logging.

        Returns:
            Tuple of (parsed_payload: dict, execution_metadata: dict)
        """
        import uuid as _uuid
        client = self.get_client()
        effective_model = model_name or self.default_model
        pages_desc = f"{len(images)} pages"

        if self.active_provider == "gemini":
            from google.genai import types
            
            # Prepare config
            config_kwargs: Dict[str, Any] = {
                "temperature": temperature,
                "response_mime_type": "application/json",
            }
            if response_schema:
                config_kwargs["response_schema"] = response_schema

            config = types.GenerateContentConfig(**config_kwargs)

            # Multimodal payload: prompt text + PIL Images
            contents: List[Any] = [prompt]
            contents.extend(images)

            start_time = time.time()
            last_err = None

            for attempt in range(1, self.max_retries + 1):
                log_id = generate_entity_id(EntityIdPrefix.API_LOG)
                attempt_start = time.time()
                try:
                    logger.info(f"🤖 AI Request -> Provider: {self.active_provider} | Model: {effective_model} | Images: {len(images)} (Attempt {attempt}/{self.max_retries})")
                    
                    response = client.models.generate_content(
                        model=effective_model,
                        contents=contents,
                        config=config
                    )
                    
                    latency_ms = (time.time() - attempt_start) * 1000.0
                    duration = time.time() - start_time
                    raw_text = response.text or "{}"
                    
                    # Parse JSON
                    clean_text = raw_text.strip()
                    if clean_text.startswith("```json"):
                        clean_text = clean_text[7:]
                    if clean_text.startswith("```"):
                        clean_text = clean_text[3:]
                    if clean_text.endswith("```"):
                        clean_text = clean_text[:-3]
                    clean_text = clean_text.strip()

                    payload = json.loads(clean_text)

                    # Extract Token Usage & Cost
                    input_tokens = 0
                    output_tokens = 0
                    if hasattr(response, "usage_metadata") and response.usage_metadata:
                        input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                        output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

                    cost_info = calculate_api_cost(
                        provider=self.active_provider,
                        model_name=effective_model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens
                    )

                    # Write SUCCESS log to api_call_logs
                    AuditLogService.log_api_call(ApiCallLogCreate(
                        log_id=log_id,
                        batch_id=batch_id,
                        company_id=company_id,
                        credential_id=None,
                        provider=self.active_provider,
                        model_name=effective_model,
                        chunk_index=chunk_index,
                        request_pages=pages_desc,
                        status_code="SUCCESS",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost_info.get("cost_usd", 0.0),
                        nominal_value_usd=cost_info.get("nominal_value_usd", 0.0),
                        is_free_tier=cost_info.get("is_free_tier", 0),
                        latency_ms=latency_ms,
                        error_reason=None,
                        raw_response=None,
                    ))

                    metadata = {
                        "provider": self.active_provider,
                        "model_name": effective_model,
                        "duration_sec": round(duration, 2),
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cost_usd": cost_info.get("cost_usd", 0.0),
                        "cost_thb": cost_info.get("cost_thb", 0.0),
                        "nominal_value_usd": cost_info.get("nominal_value_usd", 0.0),
                        "is_free_tier": cost_info.get("is_free_tier", 0),
                        "attempts": attempt
                    }

                    logger.info(f"✅ AI Extraction Completed in {duration:.2f}s | Tokens: in={input_tokens}, out={output_tokens} | Cost: ${metadata['cost_usd']:.5f} ({metadata['cost_thb']:.3f} THB)")
                    return payload, metadata

                except Exception as exc:
                    last_err = exc
                    latency_ms = (time.time() - attempt_start) * 1000.0
                    err_str = str(exc)
                    is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower()

                    # Write FAILED log to api_call_logs
                    AuditLogService.log_api_call(ApiCallLogCreate(
                        log_id=log_id,
                        batch_id=batch_id,
                        company_id=company_id,
                        credential_id=None,
                        provider=self.active_provider,
                        model_name=effective_model,
                        chunk_index=chunk_index,
                        request_pages=pages_desc,
                        status_code="FAILED",
                        input_tokens=0,
                        output_tokens=0,
                        latency_ms=latency_ms,
                        error_reason=err_str,
                    ))
                    
                    if attempt < self.max_retries:
                        sleep_sec = (2 ** attempt) + 1 if is_rate_limit else 2
                        logger.warning(f"⚠️ AI call failed on attempt {attempt}/{self.max_retries}: {exc}. Retrying in {sleep_sec}s...")
                        time.sleep(sleep_sec)
                    else:
                        logger.error(f"❌ AI call permanently failed after {self.max_retries} attempts: {exc}")

            raise RuntimeError(f"AI Service execution failed after {self.max_retries} attempts. Last error: {last_err}")

        raise NotImplementedError(f"Unsupported AI Provider: {self.active_provider}")

    def generate_raw_content(
        self,
        prompt: str,
        images: Optional[List[Image.Image]] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.0,
        batch_id: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> str:
        """
        Generates raw text response with automatic retry backoff, cached client reuse, and telemetry logging.
        """
        import uuid as _uuid
        client = self.get_client()
        effective_model = model_name or self.default_model
        pages_desc = f"{len(images)} pages" if images else "1 prompt"

        if self.active_provider == "gemini":
            from google.genai import types

            config = types.GenerateContentConfig(temperature=temperature)
            contents: List[Any] = [prompt]
            if images:
                contents.extend(images)

            last_err = None
            for attempt in range(1, self.max_retries + 1):
                log_id = generate_entity_id(EntityIdPrefix.API_LOG)
                attempt_start = time.time()
                try:
                    response = client.models.generate_content(
                        model=effective_model,
                        contents=contents,
                        config=config
                    )
                    latency_ms = (time.time() - attempt_start) * 1000.0
                    
                    # Extract Token Usage & Cost
                    input_tokens = 0
                    output_tokens = 0
                    if hasattr(response, "usage_metadata") and response.usage_metadata:
                        input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                        output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

                    cost_info = calculate_api_cost(
                        provider=self.active_provider,
                        model_name=effective_model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens
                    )

                    AuditLogService.log_api_call(ApiCallLogCreate(
                        log_id=log_id,
                        batch_id=batch_id,
                        company_id=company_id,
                        credential_id=None,
                        provider=self.active_provider,
                        model_name=effective_model,
                        chunk_index=1,
                        request_pages=pages_desc,
                        status_code="SUCCESS",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost_info.get("cost_usd", 0.0),
                        nominal_value_usd=cost_info.get("nominal_value_usd", 0.0),
                        is_free_tier=cost_info.get("is_free_tier", 0),
                        latency_ms=latency_ms,
                        error_reason=None,
                        raw_response=None,
                    ))

                    return response.text or ""
                except Exception as exc:
                    last_err = exc
                    latency_ms = (time.time() - attempt_start) * 1000.0
                    err_str = str(exc)
                    is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower()

                    AuditLogService.log_api_call(ApiCallLogCreate(
                        log_id=log_id,
                        batch_id=batch_id,
                        company_id=company_id,
                        credential_id=None,
                        provider=self.active_provider,
                        model_name=effective_model,
                        chunk_index=1,
                        request_pages=pages_desc,
                        status_code="FAILED",
                        input_tokens=0,
                        output_tokens=0,
                        latency_ms=latency_ms,
                        error_reason=err_str,
                    ))

                    if attempt < self.max_retries:
                        sleep_sec = (2 ** attempt) + 1 if is_rate_limit else 2
                        logger.warning(f"⚠️ AI generate_raw_content failed (attempt {attempt}/{self.max_retries}): {exc}. Retrying in {sleep_sec}s...")
                        time.sleep(sleep_sec)
                    else:
                        logger.error(f"❌ AI generate_raw_content permanently failed after {self.max_retries} attempts: {exc}")

            raise RuntimeError(f"AI generate_raw_content failed after {self.max_retries} attempts. Last error: {last_err}")

        raise NotImplementedError(f"Unsupported AI Provider: {self.active_provider}")

    def _call_with_key(
        self,
        api_key: str,
        prompt: str,
        images: List[Image.Image],
        response_schema: Optional[Dict[str, Any]] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.1,
        batch_id: Optional[str] = None,
        chunk_index: int = 1,
        cred_id: str = "default",
        company_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Executes a single-credential API call with exponential backoff retry.
        Records each attempt to the api_call_logs table via AuditLogService.

        Returns:
            Tuple of (parsed_payload: dict, execution_metadata: dict)
        Raises:
            RuntimeError: If all retry attempts fail.
        """
        import uuid as _uuid
        effective_model = model_name or self.default_model

        if self.active_provider == "gemini":
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            config_kwargs: Dict[str, Any] = {
                "temperature": temperature,
                "response_mime_type": "application/json",
            }
            if response_schema:
                config_kwargs["response_schema"] = response_schema
            config = types.GenerateContentConfig(**config_kwargs)

            contents: List[Any] = [prompt]
            contents.extend(images)

            last_err = None
            start_time = time.time()
            pages_desc = f"{len(images)} pages"

            for attempt in range(1, self.max_retries + 1):
                log_id = generate_entity_id(EntityIdPrefix.API_LOG)
                attempt_start = time.time()
                try:
                    logger.info(
                        f"🤖 AI Request -> Credential: '{cred_id}' | Model: {effective_model} "
                        f"| Images: {len(images)} (Attempt {attempt}/{self.max_retries})"
                    )
                    response = client.models.generate_content(
                        model=effective_model,
                        contents=contents,
                        config=config,
                    )
                    latency_ms = (time.time() - attempt_start) * 1000.0
                    duration = time.time() - start_time
                    raw_text = response.text or "{}"

                    # Strip markdown code fences if present
                    clean_text = raw_text.strip()
                    if clean_text.startswith("```json"):
                        clean_text = clean_text[7:]
                    if clean_text.startswith("```"):
                        clean_text = clean_text[3:]
                    if clean_text.endswith("```"):
                        clean_text = clean_text[:-3]
                    clean_text = clean_text.strip()

                    payload = json.loads(clean_text)

                    # Token usage
                    input_tokens = 0
                    output_tokens = 0
                    if hasattr(response, "usage_metadata") and response.usage_metadata:
                        input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                        output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

                    cost_info = calculate_api_cost(
                        provider=self.active_provider,
                        model_name=effective_model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )

                    # Write SUCCESS log
                    log_cred_id = cred_id if cred_id != "fallback_default" else None
                    AuditLogService.log_api_call(ApiCallLogCreate(
                        log_id=log_id,
                        batch_id=batch_id,
                        company_id=company_id,
                        credential_id=log_cred_id,
                        provider=self.active_provider,
                        model_name=effective_model,
                        chunk_index=chunk_index,
                        request_pages=pages_desc,
                        status_code="SUCCESS",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost_info["cost_usd"],
                        nominal_value_usd=cost_info["nominal_value_usd"],
                        is_free_tier=cost_info["is_free_tier"],
                        latency_ms=latency_ms,
                        error_reason=None,
                        raw_response=None,
                    ))

                    metadata = {
                        "provider": self.active_provider,
                        "model_name": effective_model,
                        "duration_sec": round(duration, 2),
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cost_usd": cost_info.get("cost_usd", 0.0),
                        "cost_thb": cost_info.get("cost_thb", 0.0),
                        "nominal_value_usd": cost_info.get("nominal_value_usd", 0.0),
                        "is_free_tier": cost_info.get("is_free_tier", 0),
                        "attempts": attempt,
                        "cred_id": cred_id,
                    }

                    # Inject _metadata into payload for downstream pipeline consumers
                    payload["_metadata"] = metadata

                    logger.info(
                        f"✅ AI Extraction OK in {duration:.2f}s | "
                        f"Tokens: in={input_tokens}, out={output_tokens} | "
                        f"Cost: ${metadata['cost_usd']:.5f} ({metadata['cost_thb']:.3f} THB)"
                    )
                    return payload, metadata

                except Exception as exc:
                    last_err = exc
                    latency_ms = (time.time() - attempt_start) * 1000.0
                    err_str = str(exc)
                    is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower()

                    # Write FAILED log
                    log_cred_id = cred_id if cred_id != "fallback_default" else None
                    AuditLogService.log_api_call(ApiCallLogCreate(
                        log_id=log_id,
                        batch_id=batch_id,
                        company_id=company_id,
                        credential_id=log_cred_id,
                        provider=self.active_provider,
                        model_name=effective_model,
                        chunk_index=chunk_index,
                        request_pages=pages_desc,
                        status_code="FAILED",
                        input_tokens=0,
                        output_tokens=0,
                        latency_ms=latency_ms,
                        error_reason=err_str,
                    ))

                    if attempt < self.max_retries:
                        sleep_sec = (2 ** attempt) + 1 if is_rate_limit else 2
                        logger.warning(
                            f"⚠️ Attempt {attempt}/{self.max_retries} failed for '{cred_id}': {exc}. "
                            f"Retrying in {sleep_sec}s..."
                        )
                        time.sleep(sleep_sec)
                    else:
                        logger.error(f"❌ All {self.max_retries} retries failed for credential '{cred_id}': {exc}")

            raise RuntimeError(
                f"AI call failed after {self.max_retries} attempts for credential '{cred_id}'. Last error: {last_err}"
            )

        raise NotImplementedError(f"Unsupported AI Provider: {self.active_provider}")

    def extract_with_credentials(
        self,
        prompt: str,
        images: List[Image.Image],
        credentials: List[dict],
        response_schema: Optional[Dict[str, Any]] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.1,
        batch_id: Optional[str] = None,
        chunk_index: int = 1,
        company_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Extracts structured JSON with multi-credential rotation and automatic
        deactivation of repeatedly-failing credentials.

        Iterates through provided credentials in order, falling back to the next
        credential if the current one exhausts all retry attempts.

        Args:
            credentials: List of credential dicts with keys:
                         credential_id, api_key_env, error_count, is_active
            batch_id: Optional parent batch ID for per-attempt DB logging.
            chunk_index: Chunk index for multi-chunk batch tracking.
            company_id: Optional client company UUID for multi-tenant attribution.

        Returns:
            Tuple of (extracted_payload: dict, execution_metadata: dict)
        Raises:
            RuntimeError: If all credentials are exhausted without success.
        """
        from datetime import datetime, timezone

        last_exception = None
        effective_model = model_name or self.default_model

        for cred in credentials:
            cred_id = cred["credential_id"]
            env_var = cred["api_key_env"]
            api_key = os.getenv(env_var)

            if not api_key:
                logger.warning(f"API key env '{env_var}' is not set. Skipping credential '{cred_id}'.")
                continue

            try:
                logger.info(f"Attempting extraction using credential '{cred_id}' (env: '{env_var}')...")
                payload, metadata = self._call_with_key(
                    api_key=api_key,
                    prompt=prompt,
                    images=images,
                    response_schema=response_schema,
                    model_name=effective_model,
                    temperature=temperature,
                    batch_id=batch_id,
                    chunk_index=chunk_index,
                    cred_id=cred_id,
                    company_id=company_id,
                )
                return payload, metadata

            except Exception as exc:
                last_exception = exc
                logger.error(f"Credential '{cred_id}' exhausted all retries: {exc}")

        raise RuntimeError(
            f"All {len(credentials)} credentials failed extraction. Last error: {last_exception}"
        )


# Global Singleton Instance
ai_service = AIService()
