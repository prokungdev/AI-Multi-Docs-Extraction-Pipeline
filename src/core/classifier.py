import os
import re
import json
import uuid
from typing import Optional
from PIL import Image
from src.core.logger import logger
from src.core.pdf_service import PDFService

from src.core.config_loader import (
    load_system_settings,
    load_doc_type_prompt,
    get_ai_provider_config,
    get_doc_type_config_dir,
)
from src.core.constants import PipelineAction
from src.core.storage_manager import storage_manager
from src.core.db import (
    get_or_create_merchant_auto,
    get_merchant_by_tax_id,
    sanitize_short_name,
    match_merchant_by_file_prefix
)


def fast_filename_prefix_match(
    file_path: str,
    doc_type: str = None,
    domain: str = None,
    company_code: Optional[str] = None
) -> dict | None:
    """
    Checks if filename matches any approved merchant file_prefix or tax_id.
    If matched, bypasses AI classification entirely (Zero AI Token Cost).
    """
    filename = os.path.basename(file_path)
    matched_merchant = match_merchant_by_file_prefix(filename)
    if not matched_merchant:
        return None

    target_doc_type = doc_type or domain or "expense_receipt"
    status = matched_merchant.get("status_code") or matched_merchant.get("status", "APPROVED")
    tax_id = matched_merchant.get("tax_id") or "NO_TAXID"
    short_name = matched_merchant.get("short_name") or "merchant"
    merchant_name = matched_merchant.get("merchant_name") or "Unknown Merchant"
    folder_identifier = f"{tax_id}_{short_name}" if tax_id != "NO_TAXID" else "NO_TAXID"

    if status == "PENDING":
        target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, status="PENDING", merchant_folder=folder_identifier)
        pipeline_action = PipelineAction.HOLD
    elif status == "IGNORED":
        target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, status="IGNORED", merchant_folder=folder_identifier)
        pipeline_action = PipelineAction.IGNORE
    else:
        # APPROVED
        target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, merchant_folder=folder_identifier)
        pipeline_action = PipelineAction.PROCEED

    os.makedirs(target_folder, exist_ok=True)
    logger.info(f"⚡ Zero-Cost Bypass: '{filename}' matched merchant '{merchant_name}' via prefix (Action: '{pipeline_action}').")
    return {
        "file_path": file_path,
        "tax_id": tax_id,
        "merchant_name": merchant_name,
        "short_name": short_name,
        "merchant_status": status,
        "pipeline_action": pipeline_action,
        "target_folder": target_folder,
        "folder_identifier": folder_identifier,
        "zero_cost_bypass": True
    }


def render_page_one(file_path: str, output_dir: str = None) -> str:
    """
    Renders only the first page of a PDF or returns/standardizes an image file.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        if output_dir is None:
            output_dir = os.path.dirname(file_path)
        os.makedirs(output_dir, exist_ok=True)
        out_img_path = os.path.join(
            output_dir, f"_temp_p1_{os.path.splitext(os.path.basename(file_path))[0]}.jpg"
        ).replace("\\", "/")

        pil_img = PDFService.render_page_to_pil(file_path, page_index=0, dpi=150)
        pil_img.convert("RGB").save(out_img_path, format="JPEG", quality=85)
        return out_img_path
    else:
        return file_path


def offline_text_classifier(file_path: str) -> dict:
    """
    Lightweight heuristic fallback classifier using PDFService embedded text and regex.
    """
    tax_id = ""
    merchant_name = ""
    suggested_short_name = ""

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        try:
            text = PDFService.extract_text(file_path, max_pages=1)
            if text:
                # Search for 13 digit tax id
                tax_match = re.search(r"(?:tax\s*id|เลขประจำตัวผู้เสียภาษี|tax|เลขที่ผู้เสียภาษี)?\s*:?\s*(\d{13})", text, re.IGNORECASE)
                if tax_match:
                    tax_id = tax_match.group(1)

                # Extract top lines for possible merchant name
                lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 3]
                if lines:
                    merchant_name = lines[0]
        except Exception as e:
            logger.debug(f"Offline text scan failed: {e}")

    if not merchant_name:
        base = os.path.splitext(os.path.basename(file_path))[0]
        clean_base = re.sub(r"[^a-zA-Z0-9]+", " ", base).strip()
        merchant_name = clean_base or "Unknown Merchant"

    suggested_short_name = sanitize_short_name(merchant_name)
    return {
        "tax_id": tax_id,
        "merchant_name": merchant_name,
        "suggested_short_name": suggested_short_name,
        "has_tax_id": bool(tax_id and len(tax_id) == 13)
    }


def classify_document(
    file_path: str,
    doc_type: str = None,
    domain: str = None,
    company_code: Optional[str] = None,
    configs_dir: str = "configs"
) -> dict:
    """
    Lightweight AI Ingestion Classifier for Page 1 of a document in 01_drop_zone.
    Extracts tax_id, merchant_name, and suggested_short_name, checks/creates merchants record,
    and returns routing instructions and pipeline action (PROCEED, HOLD, IGNORE).
    """
    target_doc_type = doc_type or domain or "expense_receipt"
    # 0. Check Zero-Cost Rule Match via file_prefix or Tax ID in filename
    fast_match = fast_filename_prefix_match(file_path, doc_type=target_doc_type, company_code=company_code)
    if fast_match:
        return fast_match

    comp = company_code or "C00000_SAMPLE"
    preprocess_dir = storage_manager.get_preprocess_dir(comp, target_doc_type)

    # 1. Render Page 1 only
    temp_p1_path = render_page_one(file_path, output_dir=preprocess_dir)
    
    classification_result = None
    api_key = os.getenv("GEMINI_API_KEY")

    # 2. Fast AI classification via AIService (if key available)
    if api_key:
        try:
            from src.core.ai_service import ai_service
            cfg_dir = get_doc_type_config_dir(target_doc_type, configs_dir)
            classify_prompt_path = os.path.join(cfg_dir, "classify-prompt.txt")
            
            prompt_text = "Extract tax_id (13 digits), merchant_name, and suggested_short_name from this receipt/invoice."
            if os.path.exists(classify_prompt_path):
                with open(classify_prompt_path, "r", encoding="utf-8") as f:
                    prompt_text = f.read()

            classify_schema = {
                "type": "OBJECT",
                "properties": {
                    "tax_id": {"type": "STRING", "description": "13-digit Thai Tax ID or empty string if not found"},
                    "merchant_name": {"type": "STRING", "description": "Seller / store legal or brand name"},
                    "suggested_short_name": {"type": "STRING", "description": "Short clean identifier (a-z, 0-9, _) for folder naming"},
                    "has_tax_id": {"type": "BOOLEAN", "description": "True if valid 13-digit tax id is identified"}
                },
                "required": ["tax_id", "merchant_name", "suggested_short_name", "has_tax_id"]
            }

            img = Image.open(temp_p1_path)
            classification_result, meta = ai_service.extract_structured_json(
                prompt=prompt_text,
                images=[img],
                response_schema=classify_schema,
                temperature=0.1
            )
            logger.info(f"AI Fast Classifier result: {classification_result}")
        except Exception as e:
            logger.warning(f"AI classification failed, falling back to offline scan: {e}")

    # Fallback if AI not used or failed
    if not classification_result:
        classification_result = offline_text_classifier(file_path)

    # Clean up temporary rendered page 1 image if created
    if temp_p1_path != file_path and os.path.exists(temp_p1_path):
        try:
            os.remove(temp_p1_path)
        except Exception:
            pass

    tax_id = (classification_result.get("tax_id") or "").strip()
    merchant_name = (classification_result.get("merchant_name") or "Unknown Merchant").strip()
    suggested_short_name = sanitize_short_name(
        classification_result.get("suggested_short_name") or merchant_name
    )

    # 3. Check / Auto-register in merchants table
    if tax_id and len(tax_id) == 13 and tax_id.isdigit():
        merchant, is_new = get_or_create_merchant_auto(
            tax_id=tax_id,
            merchant_name=merchant_name,
            suggested_short_name=suggested_short_name
        )
        status = merchant.get("status_code") or merchant.get("status", "PENDING")
        short_name = merchant.get("short_name", suggested_short_name)
        folder_identifier = f"{tax_id}_{short_name}"

        if status == "PENDING":
            target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, status="PENDING", merchant_folder=folder_identifier)
            pipeline_action = PipelineAction.HOLD
            logger.warning(f"Merchant '{merchant_name}' is in PENDING status. File held for review in '{target_folder}'.")
        elif status == "IGNORED":
            target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, status="IGNORED", merchant_folder=folder_identifier)
            pipeline_action = PipelineAction.IGNORE
            logger.info(f"Merchant '{merchant_name}' is in IGNORED status. File moved to '{target_folder}'.")
        else:
            # APPROVED
            target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, merchant_folder=folder_identifier)
            pipeline_action = PipelineAction.PROCEED
            logger.info(f"Merchant '{merchant_name}' is APPROVED. File ready in '{target_folder}'.")
    else:
        # No 13-digit Tax ID found -> slip / cash bill
        merchant = {"merchant_id": "merch_notax", "tax_id": "NO_TAXID", "status_code": "APPROVED", "short_name": "no_taxid"}
        target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, merchant_folder="NO_TAXID")
        pipeline_action = PipelineAction.PROCEED
        folder_identifier = "NO_TAXID"
        logger.info(f"No valid Tax ID detected for '{os.path.basename(file_path)}'. Routing to NO_TAXID folder.")

    os.makedirs(target_folder, exist_ok=True)
    return {
        "file_path": file_path,
        "tax_id": tax_id or "NO_TAXID",
        "merchant_name": merchant_name,
        "short_name": merchant.get("short_name", suggested_short_name),
        "merchant_status": merchant.get("status_code") or merchant.get("status", "APPROVED"),
        "pipeline_action": pipeline_action,
        "target_folder": target_folder,
        "folder_identifier": folder_identifier
    }


classify_drop_zone_document = classify_document
