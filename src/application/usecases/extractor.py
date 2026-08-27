import os
import json
import copy
from PIL import Image
from src.infrastructure.common.logger import logger
from src.infrastructure.common.config_loader import load_doc_type_ai_config, load_system_settings, get_ai_provider_config, get_default_doc_type
from src.infrastructure.ai.ai_service import ai_service

def clean_schema_for_structured_output(schema: dict) -> dict:
    """Converts a standard JSON Schema dictionary into the OpenAPI uppercase schema format."""
    schema_copy = copy.deepcopy(schema)
    schema_copy.pop("$schema", None)
    schema_copy.pop("title", None)
    
    def convert_types(d):
        if not isinstance(d, dict):
            return d
            
        if "type" in d and isinstance(d["type"], str):
            d["type"] = d["type"].upper()
            
        for k, v in d.items():
            if isinstance(v, dict):
                convert_types(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        convert_types(item)
        return d
        
    return convert_types(schema_copy)


def extract_document_data(
    image_paths: str | list[str],
    merchant_id: str = None,
    doc_type: str = None,
    configs_dir: str = "configs",
    batch_id: str = None,
    chunk_index: int = 1,
    company_id: str = None,
) -> dict:
    """Extracts structured data from document images using multimodal AI and configured schemas."""
    target_doc_type = doc_type or get_default_doc_type()
    merchant_key = merchant_id or "NO_TAX_LABEL"
    if isinstance(image_paths, str):
        image_paths = [image_paths]

    settings_path = os.path.join(configs_dir, "settings.json")
    settings = load_system_settings(settings_path)
    ai_cfg = get_ai_provider_config(settings)
    max_images = ai_cfg.get("max_images_per_request", 50)

    if len(image_paths) > max_images:
        error_msg = f"Number of pages ({len(image_paths)}) exceeds the maximum allowed images per request ({max_images})."
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Resolve AI provider and model configuration for this doc_type
    provider, model_name = load_doc_type_ai_config(target_doc_type, settings)
    logger.info(f"AI Config resolved for doc_type '{target_doc_type}' (merchant '{merchant_key}'): Provider='{provider}', Model='{model_name}'")

    from src.infrastructure.common.config_loader import load_doc_type_schema, load_doc_type_prompt
    raw_schema = load_doc_type_schema(target_doc_type, configs_dir=configs_dir)
        
    # 1. Clean the schema for structured output
    cleaned_schema = clean_schema_for_structured_output(raw_schema)
    
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
    prompt_text = load_doc_type_prompt(target_doc_type, configs_dir)
    if not prompt_text:
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
    
    # 4. Resolve active credentials from settings
    ai_provider_cfg = settings.get("ai_provider", {})
    provider_cfg = ai_provider_cfg.get(provider, {})
    default_env_var = provider_cfg.get("api_key_env")
    if not default_env_var:
        raise ValueError(f"Missing required 'api_key_env' for AI provider '{provider}' in {settings_path}")

    credentials = [{
        "credential_id": "default",
        "provider": provider,
        "model_name": model_name,
        "api_key_env": default_env_var,
        "is_active": 1,
        "error_count": 0
    }]

    # Delegate credential rotation, retry, and logging to AIService (Single Responsibility)
    from src.infrastructure.ai.ai_service import ai_service
    extracted_data, _metadata = ai_service.extract_with_credentials(
        prompt=prompt_text,
        images=images,
        credentials=credentials,
        response_schema=wrapped_schema,
        model_name=model_name,
        batch_id=batch_id,
        chunk_index=chunk_index,
        company_id=company_id,
    )
    return extracted_data


# ==============================================================================
# Asynchronous Concurrency Wrappers
# ==============================================================================

import asyncio

async def async_extract_document_data(
    image_paths: str | list[str],
    merchant_id: str = None,
    doc_type: str = None,
    configs_dir: str = "configs",
    batch_id: str = None,
    chunk_index: int = 1,
    company_id: str = None,
    semaphore: asyncio.Semaphore = None
) -> dict:
    """
    Asynchronously extracts structured data from image files using AI
    while enforcing concurrency limits via asyncio.Semaphore.
    """
    target_doc_type = doc_type or get_default_doc_type()
    if semaphore:
        async with semaphore:
            return await asyncio.to_thread(
                extract_document_data,
                image_paths=image_paths,
                merchant_id=merchant_id,
                doc_type=target_doc_type,
                configs_dir=configs_dir,
                batch_id=batch_id,
                chunk_index=chunk_index,
                company_id=company_id,
            )
    else:
        return await asyncio.to_thread(
            extract_document_data,
            image_paths=image_paths,
            merchant_id=merchant_id,
            doc_type=target_doc_type,
            configs_dir=configs_dir,
            batch_id=batch_id,
            chunk_index=chunk_index,
            company_id=company_id,
        )
