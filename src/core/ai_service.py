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
from loguru import logger

from src.core.config_loader import load_system_settings
from src.core.cost_estimator import calculate_api_cost
from src.core.constants import DEFAULT_SETTINGS_PATH


class AIService:
    """
    Unified LLM Client Service.
    Handles API key discovery, rate-limiting retry backoff, structured output parsing,
    and automatic token cost estimation.
    """

    def __init__(self, settings_path: str = DEFAULT_SETTINGS_PATH):
        self.settings_path = settings_path
        self._reload_config()

    def _reload_config(self):
        settings = load_system_settings(self.settings_path)
        ai_cfg = settings.get("ai_provider", {})
        self.active_provider = ai_cfg.get("active_provider", "gemini").lower()
        self.max_retries = int(ai_cfg.get("max_retries", 3))
        self.max_images_per_request = int(ai_cfg.get("max_images_per_request", 50))
        
        provider_cfg = ai_cfg.get(self.active_provider, {})
        self.default_model = provider_cfg.get("model_name", "gemini-3.5-flash")
        self.api_key_env = provider_cfg.get("api_key_env", "GEMINI_API_KEY")
        self.api_key = os.getenv(self.api_key_env, "").strip()

    def get_client(self):
        """Returns the active AI provider client instance."""
        if not self.api_key:
            self._reload_config()

        if not self.api_key:
            raise ValueError(f"AI API key environment variable '{self.api_key_env}' is not set in environment or .env file.")

        if self.active_provider == "gemini":
            from google import genai
            return genai.Client(api_key=self.api_key)
        else:
            raise NotImplementedError(f"AI Provider '{self.active_provider}' is not yet supported.")

    def extract_structured_json(
        self,
        prompt: str,
        images: List[Image.Image],
        response_schema: Optional[Dict[str, Any]] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.1
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Synchronously sends multimodal prompt + images to the configured LLM and returns parsed JSON.
        Includes built-in exponential backoff auto-retry.

        Returns:
            Tuple of (parsed_payload: dict, execution_metadata: dict)
        """
        client = self.get_client()
        effective_model = model_name or self.default_model

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
                try:
                    logger.info(f"🤖 AI Request -> Provider: {self.active_provider} | Model: {effective_model} | Images: {len(images)} (Attempt {attempt}/{self.max_retries})")
                    
                    response = client.models.generate_content(
                        model=effective_model,
                        contents=contents,
                        config=config
                    )
                    
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
                    err_str = str(exc)
                    is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower()
                    
                    if attempt < self.max_retries:
                        sleep_sec = (2 ** attempt) + 1 if is_rate_limit else 2
                        logger.warning(f"⚠️ AI call failed on attempt {attempt}/{self.max_retries}: {exc}. Retrying in {sleep_sec}s...")
                        time.sleep(sleep_sec)
                    else:
                        logger.error(f"❌ AI call permanently failed after {self.max_retries} attempts: {exc}")

            raise RuntimeError(f"AI Service execution failed after {self.max_retries} attempts. Last error: {last_err}")

        raise NotImplementedError(f"Unsupported AI Provider: {self.active_provider}")


# Global Singleton Instance
ai_service = AIService()
