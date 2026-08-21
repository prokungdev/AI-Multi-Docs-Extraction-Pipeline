import os
import json
from loguru import logger

from src.core.config_loader import load_system_settings, get_default_domain
from src.core.db import get_pages_by_status, update_page_status
from src.core.models import DocumentStatus
from src.core.pipeline.helpers import validate_and_process_payload


def validate_documents(domain: str = None) -> dict:
    """
    Stage 4: Validation & Post-Processing.
    Applies merchant rules, Tax ID verification, date conversions (BE->AD), math checks, and sets priority.
    """
    logger.info("Starting Stage 4 (Validate): Validation & Rule Processing")

    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    if domain is None:
        domain = get_default_domain()

    domain_storage = os.path.join(storage_root, domain).replace("\\", "/")
    queue_dir = os.path.join(domain_storage, "03_processing_queue").replace("\\", "/")

    if not os.path.exists(queue_dir):
        logger.warning(f"Processing queue directory not found: {queue_dir}")
        return {"validated": 0, "needs_review": 0}

    try:
        pages = get_pages_by_status([DocumentStatus.EXTRACTED.value])

        if not pages:
            logger.info("No pages found with status 'EXTRACTED' to validate.")
            return {"validated": 0, "needs_review": 0}

        logger.info(f"Found {len(pages)} extracted page(s) to validate and process...")
        validated_count = 0
        needs_review_count = 0

        for p in pages:
            page_id = p["page_id"]
            batch_id = p["batch_id"]
            page_number = p["page_number"]
            image_path = p["image_path"]
            storage_path = p["storage_path"]

            folder_name = os.path.basename(storage_path)
            source = "_default" if folder_name == "_uncategorized" else folder_name

            image_basename = os.path.splitext(os.path.basename(image_path))[0]
            json_filename = f"{image_basename}.json"
            json_path = os.path.join(queue_dir, source, json_filename).replace("\\", "/")

            if not os.path.exists(json_path):
                alt_path = os.path.join(queue_dir, json_filename).replace("\\", "/")
                if os.path.exists(alt_path):
                    json_path = alt_path
                else:
                    continue

            try:
                with open(json_path, "r", encoding="utf-8") as jf:
                    raw_payload = json.load(jf)
            except Exception as read_err:
                logger.error(f"Failed to read JSON at {json_path}: {read_err}")
                continue

            processed_payload, new_status, notes = validate_and_process_payload(raw_payload, domain, source)

            try:
                with open(json_path, "w", encoding="utf-8") as wf:
                    json.dump(processed_payload, wf, ensure_ascii=False, indent=2)
            except Exception as write_err:
                logger.error(f"Failed to save processed JSON at {json_path}: {write_err}")
                continue

            update_page_status(page_id, new_status)

            if new_status == DocumentStatus.NEEDS_REVIEW.value:
                needs_review_count += 1
                logger.warning(f"[NEEDS_REVIEW] Page {page_number} of Batch '{batch_id}': {'; '.join(notes)}")
            else:
                validated_count += 1
                logger.info(f"[PROCESSED] Page {page_number} of Batch '{batch_id}' validated successfully.")

        logger.info(f"Validation completed: {validated_count} PROCESSED, {needs_review_count} NEEDS_REVIEW")
        return {"validated": validated_count, "needs_review": needs_review_count}

    except Exception as e:
        logger.error(f"Error during validation stage: {e}")
        return {"error": str(e)}

