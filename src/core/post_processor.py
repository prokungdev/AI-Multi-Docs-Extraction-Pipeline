import os
import json
import re
import shutil
import logging
import pandas as pd
from datetime import datetime

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger("post_processor")

from src.core.db import (
    get_db_connection,
    get_document_pages,
    get_batch_pages,
    update_document_metadata,
    update_document_to_approved
)
from src.core.transformer import transform_data
from src.core.config_loader import load_source_rules

def normalize_date_to_ad(date_str: str, source_era: str = "BE") -> str:
    """
    Converts Buddhist Era (BE/พ.ศ.) years (> 2500) to Christian Era (AD/ค.ศ.) in YYYY-MM-DD format.
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

def apply_source_rules(payload: dict, domain: str, source: str) -> tuple[dict, bool, str | None]:
    """
    Applies source-specific post-processing rules onto extracted JSON payload.
    
    Returns:
        tuple of (updated_payload, requires_review, review_reason)
    """
    if not isinstance(payload, dict):
        return payload, False, None

    rules = load_source_rules(domain, source)
    post_rules = rules.get("post_processing_rules", {})
    allowed_tax_ids = [t.replace(" ", "").replace("-", "") for t in rules.get("tax_ids", []) if t]
    
    requires_review = False
    review_reasons = []

    # 1. Tax ID Verification
    merchant_obj = payload.get("merchant", {})
    extracted_tax_id = merchant_obj.get("tax_id") or payload.get("tax_id", "")
    clean_extracted_tax_id = extracted_tax_id.replace(" ", "").replace("-", "").strip() if extracted_tax_id else ""

    if source != "_default" and allowed_tax_ids:
        if not clean_extracted_tax_id:
            requires_review = True
            review_reasons.append(f"ไม่พบเลขประจำตัวผู้เสียภาษีผู้ขายในเอกสาร (ต้องการ Tax ID ของ '{source}')")
        elif clean_extracted_tax_id not in allowed_tax_ids:
            requires_review = True
            review_reasons.append(
                f"เลขประจำตัวผู้เสียภาษีผู้ขาย ('{extracted_tax_id}') ไม่ตรงกับรายการ Tax ID ที่ได้รับอนุมัติในกฎของ '{source}'"
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

def archive_and_export_document(document_id: str, payload: dict, original_pdf_name: str,
                                domain_id: str, source_id: str, settings: dict, conn=None, **kwargs) -> bool:
    """
    Performs file archiving and report exporting for an approved document.
    Copies raw file and split pages to 04_archive, deletes pages from 02_split_pages,
    and updates flattened outputs.
    """
    storage_root = settings.get("storage_root", "pipeline_storage")
    domain_storage = os.path.join(storage_root, domain_id).replace("\\", "/")
    
    # 1. Archiving Files
    archive_dir = os.path.join(domain_storage, "04_archive").replace("\\", "/")
    current_month = datetime.now().strftime("%Y-%m")
    month_archive_raw = os.path.join(archive_dir, current_month, "raw").replace("\\", "/")
    month_archive_json = os.path.join(archive_dir, current_month, "verified_json").replace("\\", "/")
    
    os.makedirs(month_archive_raw, exist_ok=True)
    os.makedirs(month_archive_json, exist_ok=True)
    
    # Find and copy original file from inbox to archive raw
    inbox_dir = os.path.join(domain_storage, "01_raw_inbox").replace("\\", "/")
    if os.path.exists(inbox_dir):
        for folder in os.listdir(inbox_dir):
            source_folder = os.path.join(inbox_dir, folder).replace("\\", "/")
            if os.path.isdir(source_folder):
                for f in os.listdir(source_folder):
                    # Check base filename match
                    if os.path.splitext(f)[0] == original_pdf_name.split(".")[0]:
                        shutil.copy(os.path.join(source_folder, f).replace("\\", "/"), os.path.join(month_archive_raw, f).replace("\\", "/"))
                        break
                        
    # Copy split pages and write JSON payload to archive
    pages = get_document_pages(document_id)
    for page in pages:
        img_path = page["image_path"]
        if os.path.exists(img_path):
            shutil.copy(img_path, os.path.join(month_archive_raw, os.path.basename(img_path)).replace("\\", "/"))
            try:
                os.remove(img_path)
            except Exception as re_err:
                logger.warning(f"Failed to remove split page image {img_path}: {re_err}")
                
    # Save final JSON in archive
    archive_json_path = os.path.join(month_archive_json, f"{document_id}.json").replace("\\", "/")
    with open(archive_json_path, "w", encoding="utf-8") as af:
        json.dump(payload, af, ensure_ascii=False, indent=2)
        
    # 2. Export outputs for all registered exporters in the domain
    try:
        from src.core.exporters import list_exporters
        exporters_list = list_exporters(domain_id)
        
        # Prepare merged document dictionary containing payload and metadata
        doc_data = {
            **payload,
            "source_id": source_id,
            "domain_id": domain_id,
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
                    
                os.makedirs("outputs", exist_ok=True)
                output_file_base = os.path.join("outputs", f"{domain_id}_{exporter_id}_export").replace("\\", "/")
                
                # Determine encoding: Express PV uses cp874 for older Thai local software compatibility
                encoding = "cp874" if exporter_id == "express_pv" else "utf-8-sig"
                
                # Write CSV
                csv_path = f"{output_file_base}.csv"
                if os.path.exists(csv_path):
                    try:
                        df_old = pd.read_csv(csv_path, encoding=encoding)
                        df_final = pd.concat([df_old, df_new], ignore_index=True)
                    except Exception:
                        df_final = df_new
                else:
                    df_final = df_new
                df_final.to_csv(csv_path, index=False, encoding=encoding)
                
                # Write JSON
                json_path = f"{output_file_base}.json"
                if os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as rf:
                            list_old = json.load(rf)
                    except Exception:
                        list_old = []
                else:
                    list_old = []
                list_old.extend(df_new.to_dict(orient="records"))
                with open(json_path, "w", encoding="utf-8") as wf:
                    json.dump(list_old, wf, ensure_ascii=False, indent=2)
            except Exception as te:
                logger.error(f"Failed to auto-export for exporter {exporter_id}: {te}")
    except Exception as re_err:
        logger.error(f"Failed to retrieve registered exporters: {re_err}")
        
    return True

def post_process_document(document_id: str, payload: dict, source_id: str, domain_id: str,
                          settings: dict, conn=None) -> dict:
    """
    Performs math validations, assigns review priority, evaluates auto-approval rules,
    and archives/exports the document if auto-approved.
    Updates the SQLite documents table metadata columns.
    
    Returns:
        A dict containing resulting metadata and status_code.
    """
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
        validation_notes.append("สูตรการเงินไม่ถูกต้อง (Subtotal - Discount + VAT != Net)")
    if items_discrepancy:
        has_ambiguous_fields = 1
        validation_notes.append("ผลรวมรายการสินค้าไม่ตรงกับยอดก่อนหักส่วนลด (Sum items != Subtotal)")
        
    if validation_notes:
        note_suffix = " [ตรวจสอบเพิ่มเติม: " + ", ".join(validation_notes) + "]"
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
    rules = load_source_rules(domain_id, source_id)
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
    
    status_code = "PROCESSED"
    auto_approved = 0
    
    # Fetch original filename for archiving
    original_pdf_name = "document.pdf"
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True
        
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT pb.original_pdf_name FROM documents doc JOIN processed_batches pb ON doc.batch_id = pb.batch_id WHERE doc.document_id = ?", (document_id,))
        row = cursor.fetchone()
        if row:
            original_pdf_name = row["original_pdf_name"]
            
        if eligible_for_auto_approve:
            status_code = "APPROVED"
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
                domain_id=domain_id,
                source_id=source_id,
                settings=settings,
                conn=conn
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
