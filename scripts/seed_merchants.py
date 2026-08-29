"""
Seed and historical data migration script using Pure SQLAlchemy 2.0 ORM.
Eradicates raw sqlite3 connections and cursor.execute calls.
"""

import sys
import os
import json
import uuid
from pathlib import Path

# Ensure src can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, update
from src.infrastructure.database.engine import get_db_session
from src.infrastructure.database.models import BatchPage, Batch, DocumentControl
from src.infrastructure.database.repositories import insert_relational_receipt
from src.infrastructure.core.constants import DocumentStatusCode, DefaultIdentifier, EntityIdPrefix, generate_entity_id
from src.infrastructure.core.logger import logger


def seed_from_queue(storage_root: str = "pipeline_storage", domain: str = DefaultIdentifier.DOC_TYPE):
    """
    Scans the 03_processing_queue folder for JSON payloads, matches them to 
    document_id in the database, and inserts them into relational tables.
    If the document record is missing, it automatically recreates it.
    """
    logger.info("Starting historical data migration from 03_processing_queue...")

    queue_dir = os.path.join(storage_root, domain, "03_processing_queue")

    if not os.path.exists(queue_dir):
        logger.error(f"Processing queue folder not found: {queue_dir}")
        return

    migrated_count = 0
    skipped_count = 0

    try:
        with get_db_session() as session:
            for root, _, files in os.walk(queue_dir):
                for file in files:
                    if file.endswith(".json") and not file.startswith("."):
                        json_path = os.path.join(root, file)
                        image_basename = os.path.splitext(file)[0]
                        source = os.path.basename(root)

                        with open(json_path, "r", encoding="utf-8") as f:
                            payload = json.load(f)

                        # Match this page image to its database page record using Pure SQLAlchemy 2.0
                        stmt = select(
                            BatchPage,
                            Batch.original_filename
                        ).join(
                            Batch, BatchPage.batch_id == Batch.batch_id
                        ).where(
                            BatchPage.image_path.like(f"%/{image_basename}.png")
                        )
                        result = session.execute(stmt).first()

                        if result:
                            doc_page, pdf_name = result
                            doc_id = doc_page.document_id
                            batch_id = doc_page.batch_id
                            page_number = doc_page.page_number

                            # Recreate document if missing
                            if not doc_id:
                                doc_id = generate_entity_id(EntityIdPrefix.DOCUMENT)
                                validation_meta = payload.get("validation_meta", {})
                                is_complete = validation_meta.get("is_complete", True)
                                missing = validation_meta.get("missing_pages", [])
                                status_code = DocumentStatusCode.PROCESSED
                                error_reason = None
                                if not is_complete:
                                    status_code = DocumentStatusCode.FAILED
                                    error_reason = f"Missing pages: {', '.join(map(str, missing))}"

                                doc_number = payload.get("doc_number", "")
                                entity_name = payload.get("merchant_name", "")
                                tax_id = payload.get("tax_id", "")
                                payment_method = payload.get("payment_method", "")
                                search_text = f"{doc_number} {entity_name} {tax_id} {payment_method}".strip()

                                new_doc = DocumentControl(
                                    document_id=doc_id,
                                    batch_id=batch_id,
                                    doc_type_id=domain,
                                    status_code=status_code,
                                    search_text=search_text,
                                    data_payload=json.dumps(payload, ensure_ascii=False),
                                    error_reason=error_reason
                                )
                                session.add(new_doc)

                                doc_page.document_id = doc_id
                                doc_page.status_code = status_code
                                doc_page.error_reason = error_reason
                                session.flush()
                                logger.info(f"Re-registered missing document record '{doc_id}' for '{file}'")

                            success = insert_relational_receipt(doc_id, payload, pdf_name)
                            if success:
                                logger.info(f"Migrated relational data for doc '{doc_id}' from '{file}'")
                                migrated_count += 1
                            else:
                                logger.error(f"Failed to migrate relational data for doc '{doc_id}' from '{file}'")
                        else:
                            logger.warning(f"No database document page found matching image basename: '{image_basename}'")
                            skipped_count += 1

        logger.info(f"Data migration finished. Successfully migrated: {migrated_count} receipt(s), skipped: {skipped_count}.")
    except Exception as e:
        logger.error(f"Failed during historical data migration: {e}")


if __name__ == "__main__":
    seed_from_queue()
