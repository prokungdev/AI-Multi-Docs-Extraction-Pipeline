import os
import json
import uuid
from loguru import logger

from src.core.config_loader import (
    load_system_settings,
    get_default_domain,
    get_default_company_code,
    get_company_pipeline_folder,
)
from src.core.db import (
    get_pages_by_status,
    update_page_status,
    create_document,
    link_pages_to_document,
    insert_relational_receipt,
    get_company_by_code,
)
from src.core.models import DocumentStatus
from src.core.post_processor import post_process_document


def transform_to_db(domain: str = None, company_code: str = None) -> dict:
    """
    Stage 5: Database Transformation.
    Imports verified/review-needed records from 04_processing into relational SQLite tables.
    """
    logger.info("Starting Stage 5 (Transform to DB): DB Transformation")

    settings = load_system_settings()
    comp_code = company_code or get_default_company_code()
    comp_info = get_company_by_code(comp_code)
    company_id = comp_info["company_id"] if comp_info else None

    if domain is None:
        domain = get_default_domain()

    from src.core.storage_manager import storage_manager
    queue_dir = storage_manager.get_processing_dir(comp_code, domain)

    try:
        pages = get_pages_by_status([
            DocumentStatus.PROCESSED.value,
            DocumentStatus.NEEDS_REVIEW.value,
            DocumentStatus.EXTRACTED.value,
        ], company_id=company_id)

        if not pages:
            logger.info(f"No pages found for DB transformation for company '{comp_code}'.")
            return {"imported": 0, "failed": 0}

        logger.info(f"Found {len(pages)} page(s) to import into DB relational tables for company '{comp_code}'...")
        imported_count = 0
        failed_count = 0

        for p in pages:
            page_id = p["page_id"]
            batch_id = p["batch_id"]
            image_path = p["image_path"]
            pdf_name = p["original_pdf_name"]
            storage_path = p["storage_path"]

            folder_name = os.path.basename(storage_path)
            from src.core.constants import NO_TAX_LABEL
            source = NO_TAX_LABEL if folder_name in ("_uncategorized", "NO_TAXID") else folder_name

            image_basename = os.path.splitext(os.path.basename(image_path))[0]
            json_filename = f"{image_basename}.json"
            json_filepath = os.path.join(queue_dir, source, json_filename).replace("\\", "/")

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

            document_id = str(uuid.uuid4())
            post_result = post_process_document(
                document_id=document_id,
                payload=extracted_data,
                source_id=source,
                domain_id=domain,
                settings=settings,
            )
            status_code = post_result.get("status_code", DocumentStatus.PROCESSED.value)

            # Extract header fields
            rec_info = extracted_data.get("receipt_info", {})
            merch_info = extracted_data.get("merchant", {})
            totals_info = extracted_data.get("totals") or extracted_data.get("financial_summary", {})

            doc_number = rec_info.get("receipt_number") or extracted_data.get("doc_number", "")
            doc_date = rec_info.get("transaction_date") or extracted_data.get("transaction_date", "")
            entity_name = merch_info.get("name") or extracted_data.get("merchant_name", "")
            total_amount = float(totals_info.get("net_amount", 0.0))
            search_text = f"{entity_name} {doc_number} {rec_info.get('expense_category', '')}".strip()

            # Extract AI and Cost metadata
            ai_meta = extracted_data.get("_metadata", {})
            model_used = ai_meta.get("model_used")
            input_tokens = ai_meta.get("input_tokens", 0)
            output_tokens = ai_meta.get("output_tokens", 0)
            cost_usd = ai_meta.get("cost_usd", 0.0)
            cost_thb = ai_meta.get("cost_thb", 0.0)
            is_free_tier = ai_meta.get("is_free_tier", 0)

            create_success = create_document(
                document_id=document_id,
                company_id=company_id,
                batch_id=batch_id,
                domain_id=domain,
                source_id=source,
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
            )

            if create_success:
                link_pages_to_document(document_id, [page_id])
                insert_relational_receipt(document_id, extracted_data, original_filename=pdf_name, company_id=company_id)
                imported_count += 1
                logger.info(f"Imported document record '{document_id}' (Company: {comp_code}, Status: {status_code})")
            else:
                failed_count += 1

        return {"imported": imported_count, "failed": failed_count}

    except Exception as e:
        logger.error(f"Error during DB transformation stage: {e}")
        return {"error": str(e)}

