"""Validation and Post-Processing Use Case.

Coordinates rule validation, priority evaluation, auto-approval, disk archiving, and output exporters.
"""

import os
import json
import shutil
from datetime import datetime
from typing import Optional, Dict, Any

from src.infrastructure.core.logger import logger
from src.infrastructure.core.config import (
    load_system_settings,
    load_doc_type_rules,
    get_default_doc_type,
    get_default_company_code,
)
from src.infrastructure.core.constants import DocumentStatusCode, DefaultIdentifier, SystemUserId
from src.infrastructure.database import (
    get_pages_by_status,
    update_page_status,
    get_company_by_code,
    get_document_pages,
    update_document_metadata,
    update_document_to_approved,
    get_db_session,
    DocumentControl,
    Batch,
)
from sqlalchemy import select
from src.application.dtos.document_dto import DocumentStatus
from src.application.pipeline.pipeline_helpers import validate_and_process_payload
from src.infrastructure.external.storage.storage_manager import storage_manager


def archive_and_export_document(
    document_id: str,
    payload: dict,
    original_pdf_name: str,
    doc_type_id: str = None,
    merchant_id: str = None,
    settings: dict = None,
    **kwargs
) -> bool:
    """
    Performs file archiving and report exporting for an approved document.
    Copies raw file and split pages to 05_archive, and updates flattened outputs in 06_output.
    """
    target_dt = doc_type_id or DefaultIdentifier.DOC_TYPE
    comp_code = kwargs.get("company_code") or get_default_company_code()

    # 1. Archiving Files
    current_month = datetime.now().strftime("%Y-%m")
    month_archive_raw = storage_manager.get_archive_dir(comp_code, target_dt, year_month=current_month, sub="raw")
    month_archive_json = storage_manager.get_archive_dir(comp_code, target_dt, year_month=current_month, sub="verified_json")

    # Find and copy original file from raw_data or drop_zone
    raw_dirs = [
        storage_manager.get_raw_data_dir(comp_code, target_dt),
        storage_manager.get_drop_zone_dir(comp_code, target_dt, "Upload"),
        storage_manager.get_drop_zone_dir(comp_code, target_dt, "Auto_Scanner")
    ]

    found_pdf = None
    for rd in raw_dirs:
        candidate = os.path.join(rd, original_pdf_name)
        if os.path.exists(candidate):
            found_pdf = candidate
            break

    if found_pdf and os.path.exists(found_pdf):
        dest_pdf = os.path.join(month_archive_raw, f"{document_id}_{original_pdf_name}")
        shutil.copy2(found_pdf, dest_pdf)
        logger.info(f"Archived raw input file to: {dest_pdf}")

    # Copy split page images
    pages = get_document_pages(document_id)
    for p in pages:
        p_path = p.get("file_path", "")
        if p_path and os.path.exists(p_path):
            p_filename = os.path.basename(p_path)
            dest_img = os.path.join(month_archive_raw, p_filename)
            shutil.copy2(p_path, dest_img)

    # Save Verified JSON
    verified_json_path = os.path.join(month_archive_json, f"{document_id}_verified.json")
    with open(verified_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved verified JSON to: {verified_json_path}")

    # 2. Trigger Exporters
    try:
        from src.application.exporters.registry import list_exporters
        exporters = list_exporters(doc_type_id=target_dt)
        for exp in exporters:
            exporter_id = exp["exporter_id"]
            handler = exp["handler"]
            try:
                flattened_doc = dict(payload)
                flattened_doc["document_id"] = document_id
                flattened_doc["original_pdf_name"] = original_pdf_name

                df = handler.transform([flattened_doc])
                if not df.empty:
                    export_dir = storage_manager.get_output_dir(comp_code, target_dt)
                    out_filename = f"{exporter_id}_{current_month}.csv"
                    out_path = os.path.join(export_dir, out_filename)
                    handler.export(df, out_path)
                    logger.info(f"Exported output using '{exporter_id}' to: {out_path}")
            except Exception as exp_err:
                logger.error(f"Failed to export via '{exporter_id}': {exp_err}")
        return True
    except Exception as e:
        logger.error(f"Error during export stage for document '{document_id}': {e}")
        return False


def post_process_document(
    document_id: str,
    payload: dict,
    merchant_id: str = None,
    doc_type_id: str = None,
    settings: dict = None,
) -> dict:
    """
    Evaluates business rules, calculates confidence scores, and determines review priority.
    """
    target_dt = doc_type_id or DefaultIdentifier.DOC_TYPE
    sys_settings = settings or load_system_settings()

    rules = load_doc_type_rules(target_dt)

    processed_payload, status_code, validation_notes = validate_and_process_payload(
        payload=payload,
        doc_type=target_dt,
        merchant_id=merchant_id,
    )

    ext_meta = processed_payload.get("extraction_metadata", {})
    confidence = float(ext_meta.get("overall_confidence", 0.85))
    review_priority = ext_meta.get("review_priority", "LOW")

    return {
        "status_code": status_code,
        "overall_confidence": confidence,
        "review_priority": review_priority,
        "validation_results": {"is_valid": len(validation_notes) == 0, "notes": validation_notes},
        "payload": processed_payload
    }


def validate_batch_documents(
    batch_id: str,
    doc_type: str = None,
    company_code: str = None
) -> dict:
    """
    Stage 4: Validation & Post-Processing Orchestration.
    """
    if not batch_id or not str(batch_id).strip():
        raise ValueError("batch_id is required for validate_batch_documents (Fail-Fast).")

    clean_batch_id = str(batch_id).strip()
    logger.info(f"Starting Stage 4 (Validation & Post-Processing) UseCase [Batch: {clean_batch_id}]")

    settings = load_system_settings()
    comp_code = company_code or get_default_company_code()
    comp_info = get_company_by_code(comp_code)
    company_id = comp_info["company_id"] if comp_info else None

    target_doc_type = doc_type or get_default_doc_type()

    try:
        with get_db_session() as session:
            stmt = select(DocumentControl, Batch).join(
                Batch, DocumentControl.batch_id == Batch.batch_id
            ).where(
                DocumentControl.batch_id == clean_batch_id,
                DocumentControl.is_closed == 0
            )
            if company_id:
                stmt = stmt.where(DocumentControl.company_id == company_id)

            docs = session.execute(stmt).all()
            if not docs:
                logger.info(f"No open documents found for validation in batch '{clean_batch_id}'.")
                return {"validated": 0, "auto_approved": 0, "needs_review": 0}

            validated_count = 0
            auto_approved_count = 0
            needs_review_count = 0

            for doc, batch in docs:
                raw_payload = {}
                if doc.data_payload:
                    try:
                        raw_payload = json.loads(doc.data_payload)
                    except Exception:
                        raw_payload = {}

                post_res = post_process_document(
                    document_id=doc.document_id,
                    payload=raw_payload,
                    merchant_id=doc.merchant_id,
                    doc_type_id=target_doc_type,
                    settings=settings
                )

                new_status = post_res["status_code"]
                priority = post_res["review_priority"]
                confidence = post_res["overall_confidence"]

                update_document_metadata(
                    document_id=doc.document_id,
                    overall_confidence=confidence,
                    review_priority=priority
                )

                if new_status == DocumentStatusCode.PROCESSED and priority == "LOW":
                    update_document_to_approved(doc.document_id, confirmed_by=SystemUserId.DEV_ADMIN)
                    archive_and_export_document(
                        document_id=doc.document_id,
                        payload=raw_payload,
                        original_pdf_name=batch.original_filename,
                        doc_type_id=target_doc_type,
                        company_code=comp_code
                    )
                    auto_approved_count += 1
                else:
                    needs_review_count += 1

                validated_count += 1

            return {
                "validated": validated_count,
                "auto_approved": auto_approved_count,
                "needs_review": needs_review_count
            }

    except Exception as e:
        logger.error(f"Error during validation usecase for batch '{clean_batch_id}': {e}")
        return {"error": str(e)}
