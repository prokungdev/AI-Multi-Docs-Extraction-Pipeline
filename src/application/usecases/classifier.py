"""
Application Use Case: Document Ingestion Classifier & Drop Zone Orchestration.
Orchestrates PDF rendering, AI classification, merchant lookup, and storage routing.
"""

import os
from typing import Optional
from PIL import Image

from src.infrastructure.core.logger import logger
from src.infrastructure.external.pdf.pdf_service import PDFService
from src.infrastructure.core.config import (
    load_doc_type_classify_prompt,
    load_doc_type_classify_schema,
    get_default_company_code,
)
from src.infrastructure.core import (
    PipelineAction,
    DefaultIdentifier,
    MerchantStatusCode,
    SystemUserId,
    get_current_user_id,
)
from src.infrastructure.external.storage.storage_manager import storage_manager
from src.infrastructure.database import (
    get_or_create_merchant_auto,
    match_merchant_by_file_prefix,
)
from src.domain.services.text_normalizer import (
    sanitize_short_name,
    evaluate_merchant_pipeline_action,
    format_merchant_folder_identifier,
)


def fast_filename_prefix_match(
    file_path: str,
    doc_type: str = None,
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

    target_doc_type = doc_type or DefaultIdentifier.DOC_TYPE
    status = matched_merchant.get("status_code") or matched_merchant.get("status", MerchantStatusCode.APPROVED)
    tax_id = matched_merchant.get("tax_id") or DefaultIdentifier.NO_TAX_ID
    short_name = matched_merchant.get("short_name") or DefaultIdentifier.DEFAULT_SHORT_NAME
    merchant_name = matched_merchant.get("merchant_name") or DefaultIdentifier.DEFAULT_MERCHANT_NAME
    folder_identifier = format_merchant_folder_identifier(tax_id, short_name)
    pipeline_action = evaluate_merchant_pipeline_action(status)

    if status == MerchantStatusCode.PENDING:
        target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, status=MerchantStatusCode.PENDING, merchant_folder=folder_identifier)
    elif status == MerchantStatusCode.IGNORED:
        target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, status=MerchantStatusCode.IGNORED, merchant_folder=folder_identifier)
    else:
        target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, merchant_folder=folder_identifier)

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
        target_dir = output_dir if (output_dir and output_dir.strip()) else (os.path.dirname(file_path) or ".")
        os.makedirs(target_dir, exist_ok=True)
        out_img_path = os.path.join(
            target_dir, f"_temp_p1_{os.path.splitext(os.path.basename(file_path))[0]}.jpg"
        ).replace("\\", "/")

        pil_img = PDFService.render_page_to_pil(file_path, page_index=0, dpi=150)
        pil_img.convert("RGB").save(out_img_path, format="JPEG", quality=85)
        return out_img_path
    else:
        return file_path


def classify_document(
    file_path: str,
    doc_type: str = None,
    company_code: Optional[str] = None,
    company_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    configs_dir: str = "configs"
) -> dict:
    """Ingestion Classifier for Page 1 of incoming documents in 01_drop_zone."""
    target_doc_type = doc_type or DefaultIdentifier.DOC_TYPE
    fast_match = fast_filename_prefix_match(file_path, doc_type=target_doc_type, company_code=company_code)
    if fast_match:
        return fast_match

    input_dir = os.path.dirname(file_path) or "."
    temp_p1_path = render_page_one(file_path, output_dir=input_dir)

    classification_result = None
    try:
        from dotenv import load_dotenv
        load_dotenv()
        from src.infrastructure.external.ai.ai_service import ai_service

        if not ai_service.api_key:
            logger.error("AI API key is not configured. Cannot perform AI document classification.")
        else:
            try:
                prompt_text = load_doc_type_classify_prompt(target_doc_type, company_code=company_code, configs_dir=configs_dir)
                classify_schema = load_doc_type_classify_schema(target_doc_type, company_code=company_code, configs_dir=configs_dir)

                img = Image.open(temp_p1_path)
                classification_result, meta = ai_service.extract_structured_json(
                    prompt=prompt_text,
                    images=[img],
                    response_schema=classify_schema,
                    temperature=0.1,
                    batch_id=batch_id,
                    company_id=company_id,
                )
                logger.info(f"AI Fast Classifier result: {classification_result}")
            except Exception as e:
                logger.error(f"AI classification failed: {e}")
    finally:
        if temp_p1_path != file_path and os.path.exists(temp_p1_path):
            try:
                os.remove(temp_p1_path)
            except Exception:
                pass

    if not classification_result:
        # Fail-fast quarantine for unclassified documents
        comp_cd = company_code or get_default_company_code()
        raw_data_dir = storage_manager.get_raw_data_dir(comp_cd, target_doc_type)
        pending_folder = os.path.join(raw_data_dir, MerchantStatusCode.PENDING).replace("\\", "/")
        os.makedirs(pending_folder, exist_ok=True)
        return {
            "file_path": file_path,
            "tax_id": DefaultIdentifier.NO_TAX_ID,
            "merchant_name": DefaultIdentifier.UNRECOGNIZED_MERCHANT_NAME,
            "short_name": DefaultIdentifier.NO_TAX_LABEL,
            "merchant_status": MerchantStatusCode.PENDING,
            "pipeline_action": PipelineAction.HOLD,
            "target_folder": pending_folder,
            "folder_identifier": DefaultIdentifier.NO_TAX_LABEL,
        }

    tax_id = (classification_result.get("tax_id") or "").strip()
    merchant_name = (classification_result.get("merchant_name") or DefaultIdentifier.DEFAULT_MERCHANT_NAME).strip()
    suggested_short_name = sanitize_short_name(
        classification_result.get("suggested_short_name") or merchant_name
    )

    # Check / Auto-register in merchants table
    if tax_id and len(tax_id) == 13 and tax_id.isdigit():
        merchant, is_new = get_or_create_merchant_auto(
            tax_id=tax_id,
            merchant_name=merchant_name,
            suggested_short_name=suggested_short_name,
            created_by=get_current_user_id()
        )
        status = merchant.get("status_code") or merchant.get("status", MerchantStatusCode.PENDING)
        short_name = merchant.get("short_name", suggested_short_name)
        folder_identifier = format_merchant_folder_identifier(tax_id, short_name)
        pipeline_action = evaluate_merchant_pipeline_action(status)

        if status == MerchantStatusCode.PENDING:
            target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, status=MerchantStatusCode.PENDING, merchant_folder=folder_identifier)
            logger.warning(f"Merchant '{merchant_name}' is in PENDING status. File held for review in '{target_folder}'.")
        elif status == MerchantStatusCode.IGNORED:
            target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, status=MerchantStatusCode.IGNORED, merchant_folder=folder_identifier)
            logger.info(f"Merchant '{merchant_name}' is in IGNORED status. File moved to '{target_folder}'.")
        else:
            # APPROVED
            target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, merchant_folder=folder_identifier)
            logger.info(f"Merchant '{merchant_name}' is APPROVED. File ready in '{target_folder}'.")
    else:
        # No 13-digit Tax ID found -> slip / cash bill
        merchant = {
            "merchant_id": "merch_notax",
            "tax_id": DefaultIdentifier.NO_TAX_ID,
            "status_code": MerchantStatusCode.APPROVED,
            "short_name": DefaultIdentifier.NO_TAX_LABEL
        }
        target_folder = storage_manager.get_raw_data_dir(company_code, target_doc_type, merchant_folder=DefaultIdentifier.NO_TAX_ID)
        pipeline_action = PipelineAction.PROCEED
        folder_identifier = DefaultIdentifier.NO_TAX_ID
        logger.info(f"No valid Tax ID detected for '{os.path.basename(file_path)}'. Routing to NO_TAXID folder.")

    os.makedirs(target_folder, exist_ok=True)
    return {
        "file_path": file_path,
        "tax_id": tax_id or DefaultIdentifier.NO_TAX_ID,
        "merchant_name": merchant_name,
        "short_name": merchant.get("short_name", suggested_short_name),
        "merchant_status": merchant.get("status_code") or merchant.get("status", MerchantStatusCode.APPROVED),
        "pipeline_action": pipeline_action,
        "target_folder": target_folder,
        "folder_identifier": folder_identifier
    }


classify_drop_zone_document = classify_document
