"""
Stage 4: Validation & Post-Processing Pipeline Stage.
Coordinates rule validation, priority evaluation, auto-approval, disk archiving, and output exporters.
"""

import os
import json
import shutil
from datetime import datetime
from typing import Optional, Dict, Any

from src.infrastructure.common.logger import logger
from src.infrastructure.common.config_loader import (
    load_system_settings,
    load_doc_type_rules,
    get_default_doc_type,
    get_default_company_code,
)
from src.infrastructure.common.constants import DocumentStatusCode, DefaultIdentifier, SystemUserId
from src.infrastructure.persistence import (
    get_pages_by_status,
    update_page_status,
    get_company_by_code,
    get_document_pages,
    update_document_metadata,
    update_document_to_approved,
    get_db_session,
    Document,
    ProcessedBatch,
)
from sqlalchemy import select
from src.application.dtos.document_dto import DocumentStatus
from src.application.pipeline.pipeline_helpers import validate_and_process_payload
from src.infrastructure.storage.storage_manager import storage_manager


def archive_and_export_document(
    document_id: str,
    payload: dict,
    original_pdf_name: str,
    doc_type_id: str = None,
    source_id: str = None,
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
        storage_manager.get_drop_zone_dir(comp_code, target_dt),
    ]
    for r_dir in raw_dirs:
        if os.path.exists(r_dir):
            for root_dir, _, files in os.walk(r_dir):
                for f in files:
                    safe_stem = os.path.basename(original_pdf_name).split(".")[0]
                    if os.path.splitext(f)[0] == safe_stem:
                        src_f = os.path.join(root_dir, f).replace("\\", "/")
                        dst_f = os.path.join(month_archive_raw, f).replace("\\", "/")
                        shutil.copy(src_f, dst_f)
                        break
                        
    # Copy split pages
    pages = get_document_pages(document_id)
    for page in pages:
        img_path = page["image_path"]
        if os.path.exists(img_path):
            shutil.copy(img_path, os.path.join(month_archive_raw, os.path.basename(img_path)).replace("\\", "/"))
            
    # Write verified JSON payload to archive
    archive_json_path = os.path.join(month_archive_json, f"{document_id}.json").replace("\\", "/")
    with open(archive_json_path, "w", encoding="utf-8") as jf:
        json.dump(payload, jf, ensure_ascii=False, indent=2)
        
    # 2. Append to Registered DocType Exporters (Output to 06_output)
    try:
        exporters_list = list_exporters(target_dt)
        doc_data = {
            "payload": payload,
            "doc_type_id": target_dt,
            "document_id": document_id,
            "original_pdf_name": original_pdf_name
        }
        
        for exp_meta in exporters_list:
            exporter_id = exp_meta["exporter_id"]
            handler = exp_meta["handler"]
            try:
                output_dir = storage_manager.get_output_dir(comp_code, target_dt)
                output_file_base = os.path.join(output_dir, f"{target_dt}_{exporter_id}_export").replace("\\", "/")
                handler.export([doc_data], output_file_base, **kwargs)
            except Exception as te:
                logger.error(f"Failed to auto-export for exporter {exporter_id}: {te}")
    except Exception as re_err:
        logger.error(f"Failed to retrieve registered exporters: {re_err}")
        
    return True


def post_process_document(
    document_id: str,
    payload: dict,
    source_id: str = None,
    doc_type_id: str = None,
    domain_id: str = None,
    settings: dict = None,
) -> dict:
    """
    Performs math validations, assigns review priority, evaluates auto-approval rules,
    and archives/exports the document if auto-approved.
    Updates the SQLite documents table metadata columns.
    """
    target_dt = doc_type_id or domain_id or get_default_doc_type()
    
    # 1. Parse extraction metadata
    ext_meta = payload.get("extraction_metadata", {})
    overall_confidence = float(ext_meta.get("overall_confidence", 0.70))
    confidence_level = ext_meta.get("confidence_level", "MEDIUM")
    is_blurry = 1 if ext_meta.get("is_blurry", False) else 0
    has_ambiguous_fields = 1 if ext_meta.get("has_ambiguous_fields", False) else 0
    confidence_notes = ext_meta.get("confidence_notes", "")
    
    # 2. Mathematical validation
    from src.domain.services.post_processor import validate_financial_math
    is_discrepant, discrepancy_notes = validate_financial_math(payload)
    if is_discrepant:
        has_ambiguous_fields = 1
        confidence_notes += f" [Validation Alert: {', '.join(discrepancy_notes)}]"
        
    # 3. Determine priority
    from src.domain.services.post_processor import evaluate_review_priority
    val_meta = payload.get("validation_meta", {})
    is_complete = val_meta.get("is_complete", True)
    review_priority = evaluate_review_priority(overall_confidence, bool(is_blurry), bool(has_ambiguous_fields), is_complete)
    
    # 4. Auto-Approval evaluation
    rules = load_doc_type_rules(target_dt)
    auto_approve_enabled = rules.get("auto_approve_enabled", False)
    auto_approve_min_confidence = float(rules.get("auto_approve_min_confidence", 0.90))
    always_review = rules.get("always_review", not auto_approve_enabled)
    
    eligible_for_auto_approve = (
        auto_approve_enabled
        and not always_review
        and overall_confidence >= auto_approve_min_confidence
        and is_blurry == 0
        and has_ambiguous_fields == 0
        and is_complete
    )
    
    status_code = DocumentStatusCode.PROCESSED
    auto_approved = 0
    
    original_pdf_name = "document.pdf"
    try:
        with get_db_session() as session:
            stmt = (
                select(ProcessedBatch.original_pdf_name)
                .join(Document, Document.batch_id == ProcessedBatch.batch_id)
                .where(Document.document_id == document_id)
            )
            result = session.scalars(stmt).first()
            if result:
                original_pdf_name = result
            
        if eligible_for_auto_approve:
            status_code = DocumentStatusCode.APPROVED
            auto_approved = 1
            logger.info(f"Document '{document_id}' qualified for Auto-Approval. Starting archiving and exporting...")
            
            fin = payload.get("totals") or payload.get("financial_summary", {})
            net_amount = float(fin.get("net_amount", 0.0))
            data_payload = json.dumps(payload, ensure_ascii=False)
            
            update_document_to_approved(
                document_id=document_id,
                doc_number=payload.get("doc_number", ""),
                doc_date=payload.get("transaction_date", ""),
                entity_name=payload.get("merchant_name", ""),
                total_amount=net_amount,
                data_payload=data_payload,
                confirmed_by=SystemUserId.AUTO_SYSTEM
            )
            
            archive_and_export_document(
                document_id=document_id,
                payload=payload,
                original_pdf_name=original_pdf_name,
                doc_type_id=target_dt,
                source_id=source_id,
                settings=settings
            )
        else:
            logger.info(f"Document '{document_id}' requires manual review (Priority: {review_priority}).")
            
        update_document_metadata(
            document_id=document_id,
            overall_confidence=overall_confidence,
            confidence_level=confidence_level,
            is_blurry=is_blurry,
            has_ambiguous_fields=has_ambiguous_fields,
            confidence_notes=confidence_notes,
            review_priority=review_priority,
            auto_approved=auto_approved,
        )
    except Exception as e:
        logger.error(f"Error in post_process_document execution for '{document_id}': {e}")
        
    return {
        "status_code": status_code,
        "overall_confidence": overall_confidence,
        "confidence_level": confidence_level,
        "is_blurry": is_blurry,
        "has_ambiguous_fields": has_ambiguous_fields,
        "confidence_notes": confidence_notes,
        "review_priority": review_priority,
        "auto_approved": auto_approved,
        "updated_payload": payload
    }


def validate_documents(
    doc_type: str = None,
    company_code: str = None
) -> dict:
    """
    Stage 4: Validation & Post-Processing.
    Applies merchant rules, Tax ID verification, date conversions (BE->AD), math checks, and sets priority.
    """
    logger.info("Starting Stage 4 (Validate): Validation & Rule Processing")

    settings = load_system_settings()
    comp_code = company_code or get_default_company_code()
    comp_info = get_company_by_code(comp_code)
    company_id = comp_info["company_id"] if comp_info else None

    target_doc_type = doc_type or get_default_doc_type()
    queue_dir = storage_manager.get_processing_dir(comp_code, target_doc_type)

    try:
        pages = get_pages_by_status([DocumentStatus.EXTRACTED.value], company_id=company_id)

        if not pages:
            logger.info(f"No pages found with status 'EXTRACTED' to validate for company '{comp_code}'.")
            return {"validated": 0, "needs_review": 0}

        logger.info(f"Found {len(pages)} extracted page(s) to validate for company '{comp_code}'...")
        validated_count = 0
        needs_review_count = 0

        for p in pages:
            page_id = p["page_id"]
            batch_id = p["batch_id"]
            page_number = p["page_number"]
            image_path = p["image_path"]
            storage_path = p["storage_path"]

            folder_name = os.path.basename(storage_path)
            source = DefaultIdentifier.NO_TAX_LABEL if folder_name in ("_uncategorized", "NO_TAXID") else folder_name

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

            processed_payload, new_status, notes = validate_and_process_payload(raw_payload, target_doc_type, source)

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
