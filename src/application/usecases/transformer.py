"""Database Transformation Use Case.

Orchestrates transforming extracted page JSON records into relational database records.
"""

import os
import json
from src.infrastructure.core.logger import logger
from src.infrastructure.core.config import (
    load_system_settings,
    get_default_doc_type,
    get_default_company_code,
)
from src.infrastructure.database import (
    get_pages_by_status,
    update_page_status,
    create_document,
    link_pages_to_document,
    insert_relational_receipt,
    get_company_by_code,
)
from src.application.dtos.document_dto import DocumentStatus
from src.infrastructure.core.constants import EntityIdPrefix, DefaultIdentifier, generate_entity_id
from src.infrastructure.external.storage.storage_manager import storage_manager
from src.application.pipeline.pipeline_helpers import extract_page_document_payload


def transform_batch_to_db(
    batch_id: str,
    doc_type: str = None,
    company_code: str = None
) -> dict:
    """
    Transforms verified/review-needed extracted records into relational SQLite tables.
    """
    if not batch_id or not str(batch_id).strip():
        raise ValueError("batch_id is required for transform_batch_to_db (Fail-Fast).")

    clean_batch_id = str(batch_id).strip()
    logger.info(f"Starting Stage 3 (Transform to DB) UseCase [Batch: {clean_batch_id}]")

    settings = load_system_settings()
    comp_code = company_code or get_default_company_code()
    comp_info = get_company_by_code(comp_code)
    company_id = comp_info["company_id"] if comp_info else None

    target_doc_type = doc_type or get_default_doc_type()
    queue_dir = storage_manager.get_processing_dir(comp_code, target_doc_type)

    try:
        pages = get_pages_by_status([
            DocumentStatus.PROCESSED.value,
            DocumentStatus.NEEDS_REVIEW.value,
            DocumentStatus.EXTRACTED.value,
        ], company_id=company_id, batch_id=clean_batch_id)

        if not pages:
            logger.info(f"No pages found for DB transformation for company '{comp_code}'.")
            return {"imported": 0, "failed": 0}

        logger.info(f"Found {len(pages)} page(s) to import into DB relational tables for company '{comp_code}'...")
        imported_count = 0
        failed_count = 0

        # Import validator usecase lazily to prevent circular dependencies
        from src.application.usecases.validator import post_process_document

        for p in pages:
            page_id = p["page_id"]
            batch_id = p["batch_id"]
            image_path = p["image_path"]
            pdf_name = p["original_pdf_name"]
            storage_path = p["storage_path"]

            folder_name = os.path.basename(storage_path)
            merchant_folder = DefaultIdentifier.NO_TAX_LABEL if folder_name in (DefaultIdentifier.NO_TAX_LABEL, DefaultIdentifier.NO_TAX_ID, "_uncategorized") else folder_name

            image_basename = os.path.splitext(os.path.basename(image_path))[0]
            json_filename = f"{image_basename}.json"
            json_filepath = os.path.join(queue_dir, merchant_folder, json_filename).replace("\\", "/")

            if not os.path.exists(json_filepath):
                alt_path = os.path.join(queue_dir, json_filename).replace("\\", "/")
                if os.path.exists(alt_path):
                    json_filepath = alt_path
                else:
                    logger.error(f"JSON not found for page {page_id} at {json_filepath}")
                    update_page_status(page_id, DocumentStatus.FAILED.value)
                    failed_count += 1
                    continue

            try:
                with open(json_filepath, "r", encoding="utf-8") as jf:
                    extracted_data = json.load(jf)
            except Exception as je:
                logger.error(f"Failed to read JSON: {je}")
                update_page_status(page_id, DocumentStatus.FAILED.value)
                failed_count += 1
                continue

            doc_payload = extract_page_document_payload(extracted_data, page_number=p.get("page_number", 1))

            document_id = generate_entity_id(EntityIdPrefix.DOCUMENT)
            post_result = post_process_document(
                document_id=document_id,
                payload=doc_payload,
                merchant_id=merchant_folder,
                doc_type_id=target_doc_type,
                settings=settings,
            )
            status_code = post_result.get("status_code", DocumentStatus.PROCESSED.value)

            # Extract header fields from unwrapped page document payload
            rec_info = doc_payload.get("receipt_info", {})
            merch_info = doc_payload.get("merchant", {})
            totals_info = doc_payload.get("totals") or doc_payload.get("financial_summary", {})

            doc_number = rec_info.get("receipt_number") or doc_payload.get("doc_number", "")
            doc_date = rec_info.get("transaction_date") or doc_payload.get("transaction_date", "")
            entity_name = merch_info.get("name") or doc_payload.get("merchant_name", "")
            total_amount = float(totals_info.get("net_amount", 0.0))
            search_text = f"{entity_name} {doc_number} {rec_info.get('expense_category', '')}".strip()

            # Extract AI and Cost metadata
            ai_meta = doc_payload.get("_metadata") or extracted_data.get("_metadata", {})
            model_used = ai_meta.get("model_used")
            input_tokens = ai_meta.get("input_tokens", 0)
            output_tokens = ai_meta.get("output_tokens", 0)
            cost_usd = ai_meta.get("cost_usd", 0.0)
            cost_thb = ai_meta.get("cost_thb", 0.0)
            is_free_tier = ai_meta.get("is_free_tier", 0)

            ext_meta = doc_payload.get("extraction_metadata", {})
            overall_confidence = float(ext_meta.get("overall_confidence", 0.70))
            confidence_level = ext_meta.get("confidence_level", "MEDIUM")
            is_blurry = 1 if ext_meta.get("is_blurry", False) else 0
            has_ambiguous = 1 if ext_meta.get("has_ambiguous_fields", False) else 0
            confidence_notes = ext_meta.get("confidence_notes", "")
            review_priority = ext_meta.get("review_priority", "LOW")

            create_success = create_document(
                document_id=document_id,
                company_id=company_id,
                batch_id=batch_id,
                doc_type_id=target_doc_type,
                merchant_id=merchant_folder,
                status_code=status_code,
                doc_number=doc_number,
                doc_date=doc_date,
                entity_name=entity_name,
                total_amount=total_amount,
                search_text=search_text,
                data_payload=json.dumps(extracted_data, ensure_ascii=False),
                model_used=model_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                cost_thb=cost_thb,
                is_free_tier=is_free_tier,
                overall_confidence=overall_confidence,
                confidence_level=confidence_level,
                is_blurry=is_blurry,
                is_ambiguous=has_ambiguous,
                confidence_notes=confidence_notes,
                review_priority=review_priority,
            )

            if create_success:
                link_pages_to_document(document_id, [page_id])
                insert_relational_receipt(document_id, doc_payload, original_filename=pdf_name, company_id=company_id, page_number=p.get("page_number", 1))
                imported_count += 1
                logger.info(f"Imported document record '{document_id}' (Company: {comp_code}, Status: {status_code})")
            else:
                failed_count += 1

        return {"imported": imported_count, "failed": failed_count}

    except Exception as e:
        logger.error(f"Error during DB transformation stage: {e}")
        return {"error": str(e)}
