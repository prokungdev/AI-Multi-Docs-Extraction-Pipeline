import os
import json
import uuid
from loguru import logger

from src.core.config_loader import load_system_settings, get_default_domain
from src.core.db import (
    get_pages_by_status,
    update_page_status,
    create_document,
    link_pages_to_document,
    insert_relational_receipt,
)
from src.core.models import DocumentStatus
from src.core.post_processor import post_process_document


def transform_to_db(domain: str = None) -> dict:
    """
    Stage 5: Database Transformation.
    Imports verified/review-needed records from 03_processing_queue into relational SQLite tables.
    """
    logger.info("Starting Stage 5 (Transform to DB): DB Transformation")

    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    if domain is None:
        domain = get_default_domain()

    domain_storage = os.path.join(storage_root, domain).replace("\\", "/")
    queue_dir = os.path.join(domain_storage, "03_processing_queue").replace("\\", "/")

    try:
        pages = get_pages_by_status([
            DocumentStatus.PROCESSED.value,
            DocumentStatus.NEEDS_REVIEW.value,
            DocumentStatus.EXTRACTED.value,
        ])

        if not pages:
            logger.info("No pages found for DB transformation.")
            return {"imported": 0, "failed": 0}

        logger.info(f"Found {len(pages)} page(s) to import into DB relational tables...")
        imported_count = 0
        failed_count = 0

        for p in pages:
            page_id = p["page_id"]
            batch_id = p["batch_id"]
            image_path = p["image_path"]
            pdf_name = p["original_pdf_name"]
            storage_path = p["storage_path"]

            folder_name = os.path.basename(storage_path)
            source = "_default" if folder_name == "_uncategorized" else folder_name

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

            create_success = create_document(
                document_id=document_id,
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
            )

            if create_success:
                link_pages_to_document(document_id, [page_id])
                insert_relational_receipt(document_id, extracted_data)
                imported_count += 1
                logger.info(f"Imported document record '{document_id}' (Status: {status_code})")
            else:
                failed_count += 1

        return {"imported": imported_count, "failed": failed_count}

    except Exception as e:
        logger.error(f"Error during DB transformation stage: {e}")
        return {"error": str(e)}

