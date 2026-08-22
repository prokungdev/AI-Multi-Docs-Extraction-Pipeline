import os
import json
import copy
import time
from datetime import datetime
from PIL import Image
import uuid
from google import genai
from google.genai import types
from loguru import logger
from src.core.config_loader import load_source_ai_config, load_system_settings, get_ai_provider_config
from src.core.db import get_active_credentials, update_credential_status, create_api_call_log

def clean_schema_for_gemini(schema: dict) -> dict:
    """
    Converts a standard JSON Schema dictionary into the OpenAPI schema format
    required by the Gemini API (e.g. uppercase types, removing root meta keys).
    """
    schema_copy = copy.deepcopy(schema)
    
    # Remove root-level metadata keys that Gemini does not support
    schema_copy.pop("$schema", None)
    schema_copy.pop("title", None)
    
    def convert_types(d):
        if not isinstance(d, dict):
            return d
            
        # Convert type values to uppercase (e.g., 'object' -> 'OBJECT')
        if "type" in d and isinstance(d["type"], str):
            d["type"] = d["type"].upper()
            
        # Recursively traverse nested items and properties
        for k, v in d.items():
            if isinstance(v, dict):
                convert_types(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        convert_types(item)
        return d
        
    return convert_types(schema_copy)

def extract_document_data(image_paths: str | list[str], source: str, domain: str, configs_dir: str = "configs",
                          batch_id: str = None, chunk_index: int = 1) -> dict:
    """
    Extracts structured data from one or more image files using the configured
    multimodal vision AI provider and domain-specific prompt/schema configurations.
    
    Args:
        image_paths: Path or list of paths to the document image files.
        source: The merchant or source identifier (e.g. 'sample_merchant' or '_default').
        domain: The document type domain name (e.g. 'expense_receipt').
        configs_dir: The root configuration directory.
        batch_id: Optional ID of the parent batch for tracking and logging.
        chunk_index: Optional index of the current chunk/part for logging.
        
    Returns:
        A dictionary containing the extracted data conforming to the domain's schema
        along with validation_meta evaluation checks.
    """
    if isinstance(image_paths, str):
        image_paths = [image_paths]

    # Load settings to check max_images_per_request
    settings_path = os.path.join(configs_dir, "settings.json")
    settings = load_system_settings(settings_path)
    ai_cfg = get_ai_provider_config(settings)
    max_images = ai_cfg.get("max_images_per_request", 50)

    if len(image_paths) > max_images:
        error_msg = f"Number of pages ({len(image_paths)}) exceeds the maximum allowed images per request ({max_images})."
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Resolve AI provider and model configuration for this source
    provider, model_name = load_source_ai_config(domain, source, settings)
    logger.info(f"AI Config resolved for source '{source}': Provider='{provider}', Model='{model_name}'")
    
    if provider != "gemini":
        err_msg = f"AI Provider '{provider}' is not supported in current implementation. Only 'gemini' is supported."
        logger.error(err_msg)
        raise NotImplementedError(err_msg)

    from src.core.config_loader import load_doc_type_schema, load_doc_type_prompt
    raw_schema = load_doc_type_schema(domain, configs_dir)
    if not raw_schema:
        # Fallback to direct path check
        domain_dir = os.path.join(configs_dir, "domains", domain)
        schema_path = os.path.join(domain_dir, "schema.json")
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                raw_schema = json.load(f)
        else:
            raise FileNotFoundError(f"Schema file not found for doc_type/domain: {domain}")
        
    # 1. Clean the schema
    cleaned_schema = clean_schema_for_gemini(raw_schema)
    
    # Inject system validation_meta and doc_number into the response schema dynamically
    if "properties" in cleaned_schema:
        cleaned_schema["properties"]["doc_number"] = {
            "type": "STRING",
            "description": "The unique invoice number, receipt number, or tax invoice ID printed on the document (e.g., INV-9999, RC2026-0001). Set to empty string if not found."
        }
        cleaned_schema["properties"]["validation_meta"] = {
            "type": "OBJECT",
            "description": "System metadata for multi-page continuity validation and logical reordering.",
            "properties": {
                "is_complete": {
                    "type": "BOOLEAN",
                    "description": "True if all scanned pages of the document are present and complete (e.g. no pages are missing based on header/footer page count indicators)."
                },
                "missing_pages": {
                    "type": "ARRAY",
                    "items": {"type": "INTEGER"},
                    "description": "List of page numbers that appear to be missing (e.g. [2] if page 1 and page 3 exist but page 2 is missing)."
                },
                "logical_page_order": {
                    "type": "ARRAY",
                    "items": {"type": "INTEGER"},
                    "description": "The sequence of logical page numbers mapped to the input images (e.g. [2, 1] if the input images were scanned out of order, representing the correct reading sequence)."
                }
            },
            "required": ["is_complete", "missing_pages", "logical_page_order"]
        }
        cleaned_schema["properties"]["extraction_metadata"] = {
            "type": "OBJECT",
            "description": "Metadata for evaluating the quality and confidence of the extraction.",
            "properties": {
                "overall_confidence": {
                    "type": "NUMBER",
                    "description": "Overall confidence score of the extraction between 0.0 (lowest) and 1.0 (highest)."
                },
                "confidence_level": {
                    "type": "STRING",
                    "description": "Categorized confidence level based on overall_confidence. Can be HIGH, MEDIUM, or LOW."
                },
                "is_blurry": {
                    "type": "BOOLEAN",
                    "description": "True if the image is blurry, out of focus, or has low resolution making reading difficult."
                },
                "has_ambiguous_fields": {
                    "type": "BOOLEAN",
                    "description": "True if there are some ambiguous, cut off, or partially unreadable fields in the document."
                },
                "confidence_notes": {
                    "type": "STRING",
                    "description": "A brief explanation in Thai summarizing why this confidence level was assigned, e.g. 'ตัวเลขชัดเจน หัวบิลและยอดรวมอ่านได้ครบถ้วน'."
                }
            },
            "required": ["overall_confidence", "confidence_level", "is_blurry", "has_ambiguous_fields", "confidence_notes"]
        }
        if "required" in cleaned_schema and isinstance(cleaned_schema["required"], list):
            if "validation_meta" not in cleaned_schema["required"]:
                cleaned_schema["required"].append("validation_meta")
            if "extraction_metadata" not in cleaned_schema["required"]:
                cleaned_schema["required"].append("extraction_metadata")

    # 2. Load the standardized prompt
    prompt_text = load_doc_type_prompt(domain, configs_dir)
    if not prompt_text:
        # Fallback to sources prompt if exists
        prompt_path = os.path.join(configs_dir, "domains", domain, "sources", "_default", "prompt.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_text = f.read()
        else:
            prompt_text = "You are an expert OCR and financial data extraction system. Extract structured data accurately according to the provided schema."
        
    # Wrap the cleaned schema in a dynamic array of documents schema
    wrapped_schema = {
        "type": "OBJECT",
        "properties": {
            "extracted_documents": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        **cleaned_schema.get("properties", {}),
                        "logical_page_number": {
                            "type": "INTEGER",
                            "description": "The 1-based page number index of the image in the input list (e.g. 1 for the first image, 2 for the second image)."
                        }
                    },
                    "required": ["logical_page_number"] + cleaned_schema.get("required", [])
                }
            }
        },
        "required": ["extracted_documents"]
    }
    
    # Append system instructions for page validation and ordering
    system_instructions = """
    
    --- SYSTEM MULTI-DOCUMENT EXTRACTION INSTRUCTIONS ---
    You are analyzing a sequence of input images. Each image page represents a separate, independent receipt or tax invoice.
    Please extract the structured data for each page individually and append it to the 'extracted_documents' array.
    
    CRITICAL RULES:
    1. Set 'logical_page_number' to the 1-based index of the page in the input list (e.g. 1 for the first image, 2 for the second image, etc.).
    2. Analyze headers, footers, and page numbers of each document page. Treat each page as a separate document unless it is explicitly indicated as a continuous multi-page invoice.
    3. Perform validation_meta checks for each page separately.
    4. STRICT "DO NOT GUESS" RULE: Do not guess or speculate on unreadable, blurred, or missing characters, words, or numbers. If a field or number is partially unreadable or cut off, DO NOT guess the value. Instead, leave the field empty or null, set 'has_ambiguous_fields' to true, lower the 'overall_confidence' score accordingly, and explain it in 'confidence_notes'.
    5. Populate the 'extraction_metadata' object:
       - Estimate the overall_confidence of your extraction on a scale of 0.0 to 1.0.
       - Set confidence_level to HIGH (overall_confidence >= 0.85), MEDIUM (0.6 <= overall_confidence < 0.85), or LOW (overall_confidence < 0.6).
       - Set is_blurry to true if the document image has focus issues, motion blur, low resolution, or is hard to read.
       - Set has_ambiguous_fields to true if any extracted values are questionable, unreadable, or left empty due to legibility.
       - Write a brief explanation in Thai for 'confidence_notes' (e.g. "ตัวเลขชัดเจน หัวบิลและยอดรวมอ่านได้ครบถ้วน" or "ภาพเบลอเล็กน้อยทำให้อ่านยอดเงินยากลำบาก" or "ตัวเลขบางตัวถูกบดบังทำให้ไม่สามารถดึงข้อมูลได้").
    """
    prompt_text += system_instructions

    # 3. Load all receipt images
    images = []
    for path in image_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Receipt image not found at: {path}")
        images.append(Image.open(path))
    
    # 4. Retrieve active credentials for this model from database
    credentials = get_active_credentials(provider, model_name)
    
    # Fallback to default ENV variable if no credentials exist in database
    if not credentials:
        logger.warning(f"No active credentials found in DB for {provider}/{model_name}. Falling back to default environment key.")
        ai_provider_cfg = settings.get("ai_provider", {})
        provider_cfg = ai_provider_cfg.get(provider, {})
        default_env_var = provider_cfg.get("api_key_env", "GEMINI_API_KEY")
        credentials = [{
            "credential_id": "fallback_default",
            "provider": provider,
            "model_name": model_name,
            "api_key_env": default_env_var,
            "is_active": 1,
            "error_count": 0
        }]
        
    last_exception = None
    for cred in credentials:
        cred_id = cred["credential_id"]
        env_var = cred["api_key_env"]
        api_key = os.getenv(env_var)
        
        if not api_key:
            logger.warning(f"API key environment variable '{env_var}' is not defined. Skipping credential '{cred_id}'.")
            continue
            
        logger.info(f"Attempting structured extraction using credential '{cred_id}' (Key env: '{env_var}')...")
        
        # Initialize client with specific API key
        client = genai.Client(api_key=api_key)
        
        # Auto-Retry logic (with exponential backoff)
        max_retries = settings.get("ai_provider", {}).get("max_retries", 3)
        for attempt in range(max_retries):
            log_id = f"api_{uuid.uuid4().hex[:12]}"
            start_time = time.time()
            pages_desc = f"{len(image_paths)} pages"
            
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[*images, prompt_text],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=wrapped_schema,
                    ),
                )
                
                # Success! Record last active timestamp
                latency_ms = (time.time() - start_time) * 1000.0
                now_str = datetime.now().isoformat()
                log_cred_id = cred_id if cred_id != "fallback_default" else None
                if log_cred_id:
                    update_credential_status(log_cred_id, last_active_at=now_str, error_count=0)
                    
                # Read and log raw API response
                result_text = response.text.strip()
                logger.info(f"Raw API Response received successfully from {model_name} (Length: {len(result_text)} chars).")
                
                # Try parsing JSON
                try:
                    extracted_data = json.loads(result_text)
                except Exception as json_err:
                    last_exception = json_err
                    logger.error(f"JSON Parsing failed: {json_err}")
                    if batch_id:
                        create_api_call_log(
                            log_id=log_id,
                            batch_id=batch_id,
                            credential_id=log_cred_id,
                            provider=provider,
                            model_name=model_name,
                            chunk_index=chunk_index,
                            request_pages=pages_desc,
                            status="FAILED",
                            input_tokens=0,
                            output_tokens=0,
                            latency_ms=latency_ms,
                            error_reason=f"JSON Parsing Error: {str(json_err)}",
                            raw_response=None
                        )
                    raise json_err
                
                usage = getattr(response, "usage_metadata", None)
                input_t = getattr(usage, "prompt_token_count", 0) if usage else 0
                output_t = getattr(usage, "candidates_token_count", 0) if usage else 0
                
                extracted_data["_metadata"] = {
                    "model_used": model_name,
                    "input_tokens": input_t,
                    "output_tokens": output_t
                }
                
                # Write SUCCESS log to SQLite
                if batch_id:
                    create_api_call_log(
                        log_id=log_id,
                        batch_id=batch_id,
                        credential_id=log_cred_id,
                        provider=provider,
                        model_name=model_name,
                        chunk_index=chunk_index,
                        request_pages=pages_desc,
                        status="SUCCESS",
                        input_tokens=input_t,
                        output_tokens=output_t,
                        latency_ms=latency_ms,
                        error_reason=None,
                        raw_response=None
                    )
                
                logger.info(f"Structured extraction completed successfully via model '{model_name}'.")
                return extracted_data
                
            except Exception as e:
                last_exception = e
                latency_ms = (time.time() - start_time) * 1000.0
                err_msg = str(e)
                log_cred_id = cred_id if cred_id != "fallback_default" else None
                
                # Write FAILED log to SQLite
                if batch_id:
                    create_api_call_log(
                        log_id=log_id,
                        batch_id=batch_id,
                        credential_id=log_cred_id,
                        provider=provider,
                        model_name=model_name,
                        chunk_index=chunk_index,
                        request_pages=pages_desc,
                        status="FAILED",
                        input_tokens=0,
                        output_tokens=0,
                        latency_ms=latency_ms,
                        error_reason=err_msg
                    )
                
                sleep_time = 2 ** (attempt + 1)
                if attempt < max_retries - 1:
                    logger.warning(f"API call attempt {attempt+1}/{max_retries} failed for '{cred_id}': {e}. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"All {max_retries} retry attempts failed for credential '{cred_id}': {e}")
                    
        # Increment error count and deactivate if necessary
        if cred_id != "fallback_default":
            new_err_count = cred.get("error_count", 0) + 1
            is_active = 1
            if new_err_count >= 3:
                is_active = 0
                logger.error(f"Credential '{cred_id}' failed 3 consecutive times. DEACTIVATING credential in database.")
            update_credential_status(cred_id, error_count=new_err_count, is_active=is_active)
            
    logger.error("All available API credentials failed to extract data.")
    raise last_exception


# ==============================================================================
# Asynchronous Concurrency Wrappers
# ==============================================================================

import asyncio

async def async_extract_document_data(image_paths: str | list[str], source: str, domain: str,
                                      configs_dir: str = "configs", batch_id: str = None,
                                      chunk_index: int = 1, semaphore: asyncio.Semaphore = None) -> dict:
    """
    Asynchronously extracts structured data from image files using Gemini AI
    while enforcing concurrency limits via asyncio.Semaphore.
    """
    if semaphore:
        async with semaphore:
            return await asyncio.to_thread(
                extract_document_data,
                image_paths=image_paths,
                source=source,
                domain=domain,
                configs_dir=configs_dir,
                batch_id=batch_id,
                chunk_index=chunk_index
            )
    else:
        return await asyncio.to_thread(
            extract_document_data,
            image_paths=image_paths,
            source=source,
            domain=domain,
            configs_dir=configs_dir,
            batch_id=batch_id,
            chunk_index=chunk_index
        )

