import os
import json
import re
import shutil
import pandas as pd
from datetime import datetime
from src.core.logger import logger

from sqlalchemy import select
from src.core.db import (
    get_db_session,
    get_document_pages,
    get_batch_pages,
    update_document_metadata,
    update_document_to_approved,
    Document,
    ProcessedBatch
)
from src.core.transformer import transform_data
from src.core.config_loader import load_doc_type_rules
from src.core.constants import DocumentStatusCode, DefaultIdentifier

def normalize_date_to_ad(date_str: str, source_era: str = "BE") -> str:
    """
    Converts Buddhist Era (BE) years (> 2500) to Christian Era (AD) in YYYY-MM-DD format.
    """
    if not date_str or not isinstance(date_str, str):
        return ""
        
    clean_date = date_str.strip()
    
    # Pattern 1: YYYY-MM-DD or YYYY/MM/DD
    m1 = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", clean_date)
    if m1:
        year = int(m1.group(1))
        month = int(m1.group(2))
        day = int(m1.group(3))
        if year > 2500:
            year -= 543
        return f"{year:04d}-{month:02d}-{day:02d}"
        
    # Pattern 2: DD/MM/YYYY or DD-MM-YYYY
    m2 = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", clean_date)
    if m2:
        day = int(m2.group(1))
        month = int(m2.group(2))
        year = int(m2.group(3))
        if year > 2500:
            year -= 543
        return f"{year:04d}-{month:02d}-{day:02d}"
        
    return clean_date

def apply_source_rules(payload: dict, doc_type: str = None, source: str = None) -> tuple[dict, bool, str | None]:
    """
    Applies doc_type post-processing rules onto extracted JSON payload.
    
    Returns:
        tuple of (updated_payload, requires_review, review_reason)
    """
    if not isinstance(payload, dict):
        return payload, False, None

    target_dt = doc_type or DefaultIdentifier.DOC_TYPE
    rules = load_doc_type_rules(target_dt)
    post_rules = rules.get("post_processing_rules", {})
    allowed_tax_ids = [t.replace(" ", "").replace("-", "") for t in rules.get("tax_ids", []) if t]
    
    requires_review = False
    review_reasons = []

    # 1. Tax ID Verification
    merchant_obj = payload.get("merchant", {})
    extracted_tax_id = merchant_obj.get("tax_id") or payload.get("tax_id", "")
    clean_extracted_tax_id = extracted_tax_id.replace(" ", "").replace("-", "").strip() if extracted_tax_id else ""

    if source not in (DefaultIdentifier.NO_TAX_LABEL, DefaultIdentifier.NO_TAX_ID) and allowed_tax_ids:
        if not clean_extracted_tax_id:
            requires_review = True
            review_reasons.append(f"Seller Tax ID not found in document (Required Tax ID for '{source}')")
        elif clean_extracted_tax_id not in allowed_tax_ids:
            requires_review = True
            review_reasons.append(
                f"Seller Tax ID ('{extracted_tax_id}') does not match approved Tax IDs for '{source}'"
            )

    # 2. Date Normalization (BE -> AD)
    date_rules = post_rules.get("date_rules", {})
    source_era = date_rules.get("source_era", "BE")
    
    receipt_info = payload.get("receipt_info", {})
    raw_date = receipt_info.get("transaction_date") or payload.get("transaction_date", "")
    if raw_date:
        normalized_date = normalize_date_to_ad(raw_date, source_era=source_era)
        if isinstance(payload.get("receipt_info"), dict):
            payload["receipt_info"]["transaction_date"] = normalized_date
        payload["transaction_date"] = normalized_date

    # 3. Expense Category Code & Financial Defaults
    expense_rules = post_rules.get("expense_rules", {})
    default_cat_code = expense_rules.get("expense_category_code", "GENERAL_EXPENSE")
    
    if isinstance(payload.get("receipt_info"), dict):
        if not payload["receipt_info"].get("expense_category_code"):
            payload["receipt_info"]["expense_category_code"] = default_cat_code

    # 4. Item Defaults (unit, currency)
    item_rules = post_rules.get("item_rules", {})
    default_unit = item_rules.get("default_unit", "")
    default_currency = item_rules.get("default_currency", "")

    items = payload.get("items", [])
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                if not item.get("unit"):
                    item["unit"] = default_unit

    totals_obj = payload.get("totals", {})
    if isinstance(totals_obj, dict):
        if not totals_obj.get("currency"):
            totals_obj["currency"] = default_currency
        payload["totals"] = totals_obj

    # Attach Post-Processing Meta
    payload["_post_processing_meta"] = {
        "source_matched": source,
        "expense_category_code": default_cat_code,
        "default_wht_rate": expense_rules.get("default_wht_rate", 0.0),
        "default_vat_rate": post_rules.get("tax_rules", {}).get("default_vat_rate", 7.0),
        "requires_review": requires_review,
        "review_reasons": review_reasons
    }

    review_reason_str = " | ".join(review_reasons) if review_reasons else None
    return payload, requires_review, review_reason_str


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
    from src.core.storage_manager import storage_manager
    target_dt = doc_type_id or DefaultIdentifier.DOC_TYPE
    comp_code = kwargs.get("company_code") or "C00000_SAMPLE"
    
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
        from src.core.exporters import list_exporters
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
                # Run the exporter transformation
                df_new = handler.transform([doc_data], **kwargs)
                if df_new.empty:
                    continue
                    
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
    conn=None
) -> dict:
    """
    Performs math validations, assigns review priority, evaluates auto-approval rules,
    and archives/exports the document if auto-approved.
    Updates the SQLite documents table metadata columns.
    
    Returns:
        A dict containing resulting metadata and status_code.
    """
    target_dt = doc_type_id or domain_id or "expense_receipt"
    # 1. Parse extraction_metadata returned by Gemini
    ext_meta = payload.get("extraction_metadata", {})
    overall_confidence = float(ext_meta.get("overall_confidence", 0.70))
    confidence_level = ext_meta.get("confidence_level", "MEDIUM")
    is_blurry = 1 if ext_meta.get("is_blurry", False) else 0
    has_ambiguous_fields = 1 if ext_meta.get("has_ambiguous_fields", False) else 0
    confidence_notes = ext_meta.get("confidence_notes", "")
    
    # 2. Mathematical Validation Checks
    fin = payload.get("totals") or payload.get("financial_summary", {})
    subtotal = float(fin.get("subtotal", 0.0))
    discount = float(fin.get("discount", 0.0))
    vat_amount = float(fin.get("vat_amount", 0.0))
    net_amount = float(fin.get("net_amount", 0.0))
    
    calculated_net = subtotal - discount + vat_amount
    net_discrepancy = abs(calculated_net - net_amount) > 0.05
    
    items = payload.get("items", [])
    item_sum = sum(float(item.get("total_price", 0.0)) for item in items)
    items_discrepancy = (item_sum > 0) and (abs(item_sum - subtotal) > 0.05)
    
    validation_notes = []
    if net_discrepancy:
        has_ambiguous_fields = 1
        validation_notes.append("Financial formula mismatch (Subtotal - Discount + VAT != Net)")
    if items_discrepancy:
        has_ambiguous_fields = 1
        validation_notes.append("Item sum does not match subtotal before discount (Sum items != Subtotal)")
        
    if validation_notes:
        note_suffix = " [Validation Alert: " + ", ".join(validation_notes) + "]"
        if note_suffix not in confidence_notes:
            confidence_notes += note_suffix
            
    # Update payload extraction_metadata with any validation findings
    if "extraction_metadata" not in payload:
        payload["extraction_metadata"] = {}
    payload["extraction_metadata"]["has_ambiguous_fields"] = (has_ambiguous_fields == 1)
    payload["extraction_metadata"]["confidence_notes"] = confidence_notes
    
    # 3. Paper/Page validation check
    val_meta = payload.get("validation_meta", {})
    is_complete = val_meta.get("is_complete", True)
    
    # 4. Priority Determination
    if overall_confidence < 0.6 or is_blurry == 1 or has_ambiguous_fields == 1 or not is_complete:
        review_priority = "HIGH"
    elif overall_confidence < 0.85:
        review_priority = "MEDIUM"
    else:
        review_priority = "LOW"
        
    # 5. Auto-Approval Rules Evaluation
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
    
    # Fetch original filename for archiving
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
            
            # Save updated payload in database
            data_payload = json.dumps(payload, ensure_ascii=False)
            update_document_to_approved(
                document_id=document_id,
                doc_number=payload.get("doc_number", ""),
                doc_date=payload.get("transaction_date", ""),
                entity_name=payload.get("merchant_name", ""),
                total_amount=net_amount,
                data_payload=data_payload,
                confirmed_by="system_auto_approve"
            )
            
            # Archive files and write output reports
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
            
        # Update metadata columns in database
        update_document_metadata(
            document_id=document_id,
            overall_confidence=overall_confidence,
            confidence_level=confidence_level,
            is_blurry=is_blurry,
            has_ambiguous_fields=has_ambiguous_fields,
            confidence_notes=confidence_notes,
            review_priority=review_priority,
            auto_approved=auto_approved,
            conn=conn
        )
    except Exception as e:
        logger.error(f"Error in post_process_document execution for '{document_id}': {e}")
    finally:
        if close_conn and conn:
            conn.close()
            
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
