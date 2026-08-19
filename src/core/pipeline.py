import os
import sys
import json
import uuid
import copy
import shutil
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

from src.core.pdf_splitter import split_pdf, process_raw_image, format_page_filename
from src.core.source_matcher import match_source
from src.core.extractor import extract_document_data
from src.core.config_loader import (
    load_system_settings,
    get_default_domain,
    is_domain_active,
    is_source_active,
    load_source_rules,
    get_image_processing_config,
    get_supported_extensions
)
from src.core.db import (
    get_db_connection,
    calculate_file_hash,
    check_duplicate_document,
    create_batch,
    create_page,
    update_page,
    update_page_status,
    create_document,
    link_pages_to_document,
    update_document_payload,
    update_document_to_failed,
    insert_relational_receipt,
    initialize_db_schema,
    initialize_log_db_schema,
    seed_initial_data,
    reset_pipeline_database
)
from src.core.initializer import (
    validate_settings_config,
    validate_domain_config,
    validate_environment,
    initialize_storage_directories
)
from src.core.post_processor import post_process_document, apply_source_rules
from src.core.utils import chunk_list
from src.core.logger import setup_logger

# ==============================================================================
# Helper Functions
# ==============================================================================

def merge_chunk_payloads(payloads: list[dict]) -> dict:
    """
    Merges multiple extracted JSON payloads from different requests of the same batch.
    Combines item lists, aggregates token metadata, and computes composite validation status.
    """
    if not payloads:
        return {}
        
    if len(payloads) == 1:
        return payloads[0]
        
    merged = copy.deepcopy(payloads[0])
    
    # 1. Merge Line Items from subsequent chunks
    all_items = []
    for p in payloads:
        items = p.get("items", [])
        if isinstance(items, list):
            all_items.extend(items)
    merged["items"] = all_items
    
    # 2. Attribute and Aggregate Token Metadata across chunks
    total_input_tokens = 0
    total_output_tokens = 0
    model_name = None
    
    for p in payloads:
        meta = p.get("_metadata", {})
        if meta:
            total_input_tokens += meta.get("input_tokens", 0)
            total_output_tokens += meta.get("output_tokens", 0)
            if not model_name:
                model_name = meta.get("model_used")
                
    merged["_metadata"] = {
        "model_used": model_name,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_parts_merged": len(payloads)
    }
    
    # 3. Consolidate Validation Metadata across all parts
    is_complete = True
    missing_pages = []
    logical_page_order = []
    
    current_page_offset = 0
    for p in payloads:
        meta = p.get("validation_meta", {})
        part_complete = meta.get("is_complete", True)
        if not part_complete:
            is_complete = False
            missing_pages.extend(meta.get("missing_pages", []))
            
        part_order = meta.get("logical_page_order", [])
        offset_order = [idx + current_page_offset for idx in part_order]
        logical_page_order.extend(offset_order)
        
        current_page_offset += len(part_order) if part_order else 50
        
    merged["validation_meta"] = {
        "is_complete": is_complete,
        "missing_pages": sorted(list(set(missing_pages))),
        "logical_page_order": logical_page_order
    }
    
    return merged

def validate_and_process_payload(payload: dict, domain: str, source: str) -> tuple[dict, str, list[str]]:
    """
    Applies source validation rules, financial math checks, and sets review priority.
    """
    validation_notes = []
    
    # 1. Apply Merchant Rules (Tax ID, Date BE->AD, Default Categories/Units)
    processed_payload, req_review, review_reason = apply_source_rules(payload, domain, source)
    if req_review and review_reason:
        validation_notes.append(review_reason)
        
    # 2. Mathematical Validation Checks
    fin = processed_payload.get("totals") or processed_payload.get("financial_summary", {})
    subtotal = float(fin.get("subtotal", 0.0))
    discount = float(fin.get("discount", 0.0))
    vat_amount = float(fin.get("vat_amount", 0.0))
    net_amount = float(fin.get("net_amount", 0.0))
    
    calculated_net = subtotal - discount + vat_amount
    if abs(calculated_net - net_amount) > 0.05:
        validation_notes.append(f"Financial formula mismatch: Calculated ({subtotal:.2f} - {discount:.2f} + {vat_amount:.2f} = {calculated_net:.2f}) != Net ({net_amount:.2f})")
        
    items = processed_payload.get("items", [])
    if items:
        item_sum = sum(float(item.get("total_price", 0.0)) for item in items if isinstance(item, dict))
        if item_sum > 0 and abs(item_sum - subtotal) > 0.05:
            validation_notes.append(f"Items total price sum ({item_sum:.2f}) does not match subtotal ({subtotal:.2f})")

    # 3. Extraction Quality & Ambiguity Checks
    ext_meta = processed_payload.get("extraction_metadata", {})
    overall_confidence = float(ext_meta.get("overall_confidence", 0.75))
    is_blurry = ext_meta.get("is_blurry", False)
    has_ambiguous_fields = ext_meta.get("has_ambiguous_fields", False) or len(validation_notes) > 0
    confidence_notes = ext_meta.get("confidence_notes", "")
    
    val_meta = processed_payload.get("validation_meta", {})
    is_complete = val_meta.get("is_complete", True)
    
    # 4. Determine Review Priority
    if overall_confidence < 0.6 or is_blurry or has_ambiguous_fields or not is_complete:
        review_priority = "HIGH"
    elif overall_confidence < 0.85:
        review_priority = "MEDIUM"
    else:
        review_priority = "LOW"

    # 5. Determine Final Status Code
    if validation_notes or is_blurry or not is_complete or overall_confidence < 0.70:
        status_code = "NEEDS_REVIEW"
    else:
        status_code = "PROCESSED"
        
    if validation_notes:
        note_str = " | ".join(validation_notes)
        confidence_notes = f"{confidence_notes} [Validation: {note_str}]".strip()
        
    processed_payload["extraction_metadata"] = {
        **ext_meta,
        "overall_confidence": overall_confidence,
        "review_priority": review_priority,
        "is_blurry": is_blurry,
        "has_ambiguous_fields": has_ambiguous_fields,
        "confidence_notes": confidence_notes
    }
    
    return processed_payload, status_code, validation_notes

# ==============================================================================
# Pipeline Service Stages
# ==============================================================================

def run_init(settings_path: str = "configs/settings.json") -> bool:
    """
    Stage 1: System Initialization & Health Check.
    Validates settings.json, domain configs, Python environment, storage folders, and database schemas.
    """
    setup_logger(settings_path)
    logger.info("=========================================================")
    logger.info("  Stage 1 (Init): System Initialization & Health Check")
    logger.info("=========================================================")
    
    # 1. Validate central settings.json
    logger.info("[1/4] Checking Central settings.json...")
    settings_valid, settings_errors = validate_settings_config(settings_path)
    if not settings_valid:
        logger.error("[FAIL] settings.json has validation errors:")
        for err in settings_errors:
            logger.error(f"     - {err}")
        return False
    logger.info("[PASS] settings.json is valid and complete.")
    
    # 2. Validate domains
    settings = load_system_settings(settings_path)
    domains_data = settings.get("domains", [])
    active_domains = [d.get("domain_id") for d in domains_data if isinstance(d, dict) and d.get("is_active", True) and d.get("domain_id")]
    if not active_domains:
        active_domains = ["expense_receipt"]
        
    logger.info("[2/4] Checking Domain-specific configurations...")
    for domain in active_domains:
        logger.info(f"  * Checking domain '{domain}'...")
        domain_valid, domain_errors = validate_domain_config(domain)
        if not domain_valid:
            logger.error(f"    [FAIL] Domain '{domain}' has configuration errors:")
            for err in domain_errors:
                logger.error(f"       - {err}")
            return False
        logger.info(f"    [PASS] Domain '{domain}' configs are valid.")
        
    # 3. Check environment & packages
    logger.info("[3/4] Checking Environment & Package Dependencies...")
    env_warnings = validate_environment()
    has_errors = any("[ERROR]" in msg for msg in env_warnings)
    if has_errors:
        logger.error("[FAIL] System is missing required dependencies:")
        for msg in env_warnings:
            logger.error(f"     - {msg}")
        return False
    logger.info("[PASS] All required Python packages are installed.")
    for msg in env_warnings:
        if "[WARNING]" in msg:
            logger.warning(f"     - {msg}")
            
    # 4. Initialize storage directories & Database Schema
    logger.info("[4/4] Initializing Pipeline Storage Directories & DB Schema...")
    initialize_log_db_schema()
    initialize_db_schema()
    seed_initial_data()
    dir_count = initialize_storage_directories(settings_path)
    logger.info(f"[PASS] Ensured {dir_count} directories are created with .gitkeep.")
    
    logger.info("=========================================================")
    logger.info("[SYSTEM STATUS] System is READY and fully configured!")
    logger.info("=========================================================")
    return True

def run_split_and_match(domain: str = None, input_file: str = None, input_pdf: str = None) -> list[dict]:
    """
    Stage 2: Split multi-page PDFs or process raw images into optimized page images and match merchant source.
    """
    setup_logger()
    logger.info("=========================================================")
    logger.info("  Stage 2 (Split & Match): Processing Files & Matching Sources")
    logger.info("=========================================================")
    
    if input_file is None and input_pdf is not None:
        input_file = input_pdf
    
    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    if domain is None:
        domain = get_default_domain()
        
    img_cfg = get_image_processing_config(settings)
    supported_exts = get_supported_extensions(settings)
    processing_fmt = img_cfg["processing_format"]
    jpeg_quality = img_cfg["jpeg_quality"]
    max_dim = img_cfg["max_dimension"]
    dpi = img_cfg["dpi"]
    filename_pattern = img_cfg.get("split_filename_pattern") or img_cfg.get("filename_pattern", "{domain}_{source}_{original_filename}_{batch_id}_p{page_no}")
    
    domain_storage = os.path.join(storage_root, domain).replace("\\", "/")
    inbox_dir = os.path.join(domain_storage, "01_raw_inbox").replace("\\", "/")
    split_dir = os.path.join(domain_storage, "02_split_pages").replace("\\", "/")
    
    os.makedirs(inbox_dir, exist_ok=True)
    os.makedirs(split_dir, exist_ok=True)
    
    # Identify files to process
    files_to_process = []
    if input_file:
        if os.path.exists(input_file):
            files_to_process.append(input_file)
        else:
            logger.error(f"Input file not found: {input_file}")
            return []
    else:
        for root_dir, _, files in os.walk(inbox_dir):
            for file in files:
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in supported_exts and not file.startswith("."):
                    files_to_process.append(os.path.join(root_dir, file).replace("\\", "/"))
                    
    if not files_to_process:
        logger.info(f"No valid document files {supported_exts} found in raw inbox to process.")
        return []
        
    logger.info(f"Found {len(files_to_process)} document file(s) to process.")
    results = []
    
    for file_path in files_to_process:
        filename = os.path.basename(file_path)
        file_ext = os.path.splitext(filename)[1].lower()
        is_pdf = file_ext == ".pdf"
        
        logger.info(f"\n--- Processing: {filename} ({'PDF Document' if is_pdf else 'Direct Image'}) ---")
        
        # 1. Check Duplicate
        file_hash = calculate_file_hash(file_path)
        is_duplicate, dup_meta = check_duplicate_document(file_hash)
        if is_duplicate:
            logger.warning(f"Duplicate document detected! Already processed in Batch '{dup_meta['batch_id']}' (Status: '{dup_meta['status']}')")
            continue
            
        # 2. Match Source
        matched_source = match_source(file_path, domain=domain, settings=settings)
        logger.info(f"Matched source: '{matched_source}'")
        
        # Check source active state
        if not is_source_active(domain, matched_source):
            logger.warning(f"Source '{matched_source}' is currently DEACTIVATED in DB. Routing to '_uncategorized'.")
            matched_source = "_uncategorized"
            
        # 3. Resolve destination folder and move original file
        dest_folder = os.path.join(inbox_dir, matched_source).replace("\\", "/")
        os.makedirs(dest_folder, exist_ok=True)
        dest_file_path = os.path.join(dest_folder, filename).replace("\\", "/")
        
        if os.path.abspath(file_path) != os.path.abspath(dest_file_path):
            shutil.move(file_path, dest_file_path)

        # 4. Process Pages (PDF Splitting or Direct Image Processing)
        batch_id = str(uuid.uuid4())
        created_pages = []
        
        if is_pdf:
            try:
                page_images = split_pdf(
                    pdf_path=dest_file_path,
                    output_dir=split_dir,
                    dpi=dpi,
                    image_format=processing_fmt,
                    quality=jpeg_quality,
                    max_dimension=max_dim
                )
                total_pages = len(page_images)
            except Exception as e:
                logger.error(f"Failed to split PDF '{filename}': {e}")
                continue
                
            create_batch(
                batch_id=batch_id,
                original_pdf_name=filename,
                total_pages=total_pages,
                storage_path=dest_folder,
                file_hash=file_hash
            )
            
            for idx, temp_img_path in enumerate(page_images, start=1):
                page_id = str(uuid.uuid4())
                page_filename = format_page_filename(
                    pattern=filename_pattern,
                    domain=domain,
                    source=matched_source,
                    original_filename=filename,
                    page_no=idx,
                    batch_id=batch_id,
                    image_format=processing_fmt
                )
                final_img_path = os.path.join(split_dir, page_filename).replace("\\", "/")
                
                if os.path.exists(temp_img_path):
                    if os.path.exists(final_img_path):
                        os.remove(final_img_path)
                    os.rename(temp_img_path, final_img_path)
                    
                create_page(
                    page_id=page_id,
                    batch_id=batch_id,
                    page_number=idx,
                    image_path=final_img_path,
                    status_code="PREPROCESSED"
                )
                created_pages.append(final_img_path)
        else:
            # Standalone raw image
            total_pages = 1
            page_id = str(uuid.uuid4())
            page_filename = format_page_filename(
                pattern=filename_pattern,
                domain=domain,
                source=matched_source,
                original_filename=filename,
                page_no=1,
                batch_id=batch_id,
                image_format=processing_fmt
            )
            final_img_path = os.path.join(split_dir, page_filename).replace("\\", "/")
            
            try:
                process_raw_image(
                    image_path=dest_file_path,
                    output_dir=split_dir,
                    output_filename=page_filename,
                    image_format=processing_fmt,
                    quality=jpeg_quality,
                    max_dimension=max_dim
                )
            except Exception as e:
                logger.error(f"Failed to process raw image '{filename}': {e}")
                continue
                
            create_batch(
                batch_id=batch_id,
                original_pdf_name=filename,
                total_pages=total_pages,
                storage_path=dest_folder,
                file_hash=file_hash
            )
            
            create_page(
                page_id=page_id,
                batch_id=batch_id,
                page_number=1,
                image_path=final_img_path,
                status_code="PREPROCESSED"
            )
            created_pages.append(final_img_path)
            
        logger.info(f"Registered Batch '{batch_id}' with {total_pages} page(s) as PREPROCESSED.")
        results.append({
            "batch_id": batch_id,
            "filename": filename,
            "matched_source": matched_source,
            "total_pages": total_pages,
            "page_images": created_pages
        })
        
    return results

def run_extract(domain: str = None, source: str = None) -> dict:
    """
    Stage 3: AI Document Extraction.
    Extracts structured JSON data from preprocessed images and saves to 03_processing_queue.
    """
    setup_logger()
    logger.info("=========================================================")
    logger.info("  Stage 3 (Extract): AI Document Extraction to JSON Queue")
    logger.info("=========================================================")
    
    load_dotenv()
    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    max_images = settings.get("max_images_per_request", 50)
    if domain is None:
        domain = get_default_domain()
        
    domain_storage = os.path.join(storage_root, domain).replace("\\", "/")
    queue_dir = os.path.join(domain_storage, "03_processing_queue").replace("\\", "/")
    os.makedirs(queue_dir, exist_ok=True)
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query PREPROCESSED or PENDING batches
        cursor.execute("""
            SELECT DISTINCT pb.batch_id, pb.original_pdf_name, pb.storage_path, pb.total_pages
            FROM processed_batches pb
            JOIN document_pages dp ON pb.batch_id = dp.batch_id
            WHERE dp.status_code IN ('PREPROCESSED', 'PENDING')
        """)
        batches = cursor.fetchall()
        conn.close()
        conn = None
        
        if not batches:
            logger.info("No unextracted batches found to process.")
            return {"success": True, "batches_processed": 0, "documents_extracted": 0}
            
        logger.info(f"Found {len(batches)} batch(es) to extract with AI...")
        
        success_batches = 0
        total_docs = 0
        
        for b in batches:
            batch_id = b["batch_id"]
            pdf_name = b["original_pdf_name"]
            storage_path = b["storage_path"]
            
            # Resolve source
            folder_name = os.path.basename(storage_path)
            batch_source = "_default" if folder_name == "_uncategorized" else folder_name
            if source and source != batch_source:
                continue
                
            # Fetch page images
            batch_conn = get_db_connection()
            b_cursor = batch_conn.cursor()
            b_cursor.execute("SELECT page_id, page_number, image_path FROM document_pages WHERE batch_id = ? ORDER BY page_number ASC", (batch_id,))
            pages = b_cursor.fetchall()
            batch_conn.close()
            
            if not pages:
                continue
                
            image_paths = [p["image_path"] for p in pages if os.path.exists(p["image_path"])]
            if not image_paths:
                logger.warning(f"No valid image files found on disk for batch '{batch_id}'")
                continue
                
            logger.info(f"\n--- Extracting Batch: {batch_id} ({pdf_name}) | Source: '{batch_source}' ---")
            
            # Chunk pages if exceeding max_images
            chunks = list(chunk_list(image_paths, max_images))
            chunk_payloads = []
            failed = False
            
            for chunk_idx, chunk in enumerate(chunks, start=1):
                try:
                    payload = extract_document_data(
                        image_paths=chunk,
                        source=batch_source,
                        domain=domain,
                        batch_id=batch_id,
                        chunk_index=chunk_idx
                    )
                    chunk_payloads.append(payload)
                except Exception as ex_err:
                    logger.error(f"AI extraction failed for batch '{batch_id}' chunk {chunk_idx}: {ex_err}")
                    failed = True
                    break
                    
            if failed or not chunk_payloads:
                continue
                
            # Merge chunks
            merged_payload = merge_chunk_payloads(chunk_payloads)
            
            # Save raw extracted JSON in 03_processing_queue
            source_queue_dir = os.path.join(queue_dir, batch_source).replace("\\", "/")
            os.makedirs(source_queue_dir, exist_ok=True)
            
            for p in pages:
                image_basename = os.path.splitext(os.path.basename(p["image_path"]))[0]
                json_path = os.path.join(source_queue_dir, f"{image_basename}.json").replace("\\", "/")
                with open(json_path, "w", encoding="utf-8") as qf:
                    json.dump(merged_payload, qf, ensure_ascii=False, indent=2)
                update_page_status(p["page_id"], "EXTRACTED")
                
            logger.info(f"AI extraction completed for batch '{batch_id}'. Status set to EXTRACTED.")
            success_batches += 1
            total_docs += 1
            
        return {"success": True, "batches_processed": success_batches, "documents_extracted": total_docs}
        
    except Exception as e:
        logger.error(f"Error during AI extraction stage: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if conn:
            conn.close()

def run_validate(domain: str = None) -> dict:
    """
    Stage 4: Validation & Post-Processing.
    Applies merchant rules, Tax ID verification, date conversions (BE->AD), math checks, and sets priority.
    """
    setup_logger()
    logger.info("=========================================================")
    logger.info("  Stage 4 (Validate): Validation & Rule Processing")
    logger.info("=========================================================")
    
    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    if domain is None:
        domain = get_default_domain()
        
    domain_storage = os.path.join(storage_root, domain).replace("\\", "/")
    queue_dir = os.path.join(domain_storage, "03_processing_queue").replace("\\", "/")
    
    if not os.path.exists(queue_dir):
        logger.warning(f"Processing queue directory not found: {queue_dir}")
        return {"validated": 0, "needs_review": 0}
        
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dp.page_id, dp.batch_id, dp.page_number, dp.image_path, 
                   pb.original_pdf_name, pb.storage_path
            FROM document_pages dp
            JOIN processed_batches pb ON dp.batch_id = pb.batch_id
            WHERE dp.status_code = 'EXTRACTED'
            ORDER BY dp.batch_id, dp.page_number ASC
        """)
        pages = cursor.fetchall()
        conn.close()
        conn = None
        
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
            
            if new_status == "NEEDS_REVIEW":
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
    finally:
        if conn:
            conn.close()

def run_transform_to_db(domain: str = None) -> dict:
    """
    Stage 5: Database Transformation.
    Imports verified/review-needed records from 03_processing_queue into relational SQLite tables.
    """
    setup_logger()
    logger.info("=========================================================")
    logger.info("  Stage 5 (Transform to DB): DB Transformation")
    logger.info("=========================================================")
    
    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    if domain is None:
        domain = get_default_domain()
        
    domain_storage = os.path.join(storage_root, domain).replace("\\", "/")
    queue_dir = os.path.join(domain_storage, "03_processing_queue").replace("\\", "/")
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dp.page_id, dp.batch_id, dp.page_number, dp.image_path, 
                   pb.original_pdf_name, pb.storage_path
            FROM document_pages dp
            JOIN processed_batches pb ON dp.batch_id = pb.batch_id
            WHERE dp.status_code IN ('PROCESSED', 'NEEDS_REVIEW', 'EXTRACTED')
            ORDER BY dp.batch_id, dp.page_number ASC
        """)
        pages = cursor.fetchall()
        conn.close()
        conn = None
        
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
                    update_page_status(page_id, "FAILED")
                    failed_count += 1
                    continue
                    
            try:
                with open(json_filepath, "r", encoding="utf-8") as jf:
                    extracted_data = json.load(jf)
            except Exception as je:
                logger.error(f"Failed to read JSON: {je}")
                update_page_status(page_id, "FAILED")
                failed_count += 1
                continue
                
            document_id = str(uuid.uuid4())
            post_result = post_process_document(
                document_id=document_id,
                payload=extracted_data,
                source_id=source,
                domain_id=domain,
                settings=settings
            )
            status_code = post_result.get("status_code", "PROCESSED")
            
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
                data_payload=json.dumps(extracted_data, ensure_ascii=False)
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
    finally:
        if conn:
            conn.close()

def run_export_outputs(domain: str = None) -> dict:
    """
    Stage 6: Output Reports Generation.
    Exports all approved documents to registered exporters (CSV / Excel / Express PV).
    """
    setup_logger()
    logger.info("=========================================================")
    logger.info("  Stage 6 (Export): Generating Dynamic Output Reports")
    logger.info("=========================================================")
    
    settings = load_system_settings()
    if domain is None:
        domain = get_default_domain()
        
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.*, pb.original_pdf_name
            FROM documents d
            JOIN processed_batches pb ON d.batch_id = pb.batch_id
            WHERE d.domain_id = ? AND d.status_code IN ('APPROVED', 'PROCESSED')
            ORDER BY d.created_at ASC
        """, (domain,))
        documents = cursor.fetchall()
        conn.close()
        conn = None
        
        if not documents:
            logger.info("No documents found to export.")
            return {"exported": 0}
            
        logger.info(f"Found {len(documents)} document(s) to process for exporter outputs...")
        
        from src.core.exporters import list_exporters
        exporters_list = list_exporters(domain)
        
        if not exporters_list:
            logger.warning(f"No output exporters registered for domain '{domain}'.")
            return {"exported": 0}
            
        doc_records = []
        for doc in documents:
            payload_str = doc["data_payload"]
            try:
                payload = json.loads(payload_str) if payload_str else {}
            except Exception:
                payload = {}
                
            doc_records.append({
                **payload,
                "source_id": doc["source_id"],
                "domain_id": doc["domain_id"],
                "document_id": doc["document_id"],
                "original_pdf_name": doc["original_pdf_name"]
            })
            
        os.makedirs("outputs", exist_ok=True)
        exported_files = []
        
        for exp in exporters_list:
            exp_id = exp["exporter_id"]
            handler = exp["handler"]
            
            try:
                kwargs = {}
                if exp["has_custom_params"]:
                    kwargs = {"start_seq_no": 1, "voucher_prefix": "PV2608-"}
                    
                df_out = handler.transform(doc_records, **kwargs)
                if df_out.empty:
                    continue
                    
                out_base = os.path.join("outputs", f"{domain}_{exp_id}_export").replace("\\", "/")
                encoding = getattr(handler, "encoding", "utf-8-sig")
                
                # Write CSV
                csv_path = f"{out_base}.csv"
                df_out.to_csv(csv_path, index=False, encoding=encoding)
                exported_files.append(csv_path)
                logger.info(f"Generated CSV export: '{csv_path}'")
                
                # Write JSON
                json_path = f"{out_base}.json"
                with open(json_path, "w", encoding="utf-8") as jf:
                    json.dump(df_out.to_dict(orient="records"), jf, ensure_ascii=False, indent=2)
                exported_files.append(json_path)
                
            except Exception as ee:
                logger.error(f"Failed to run exporter '{exp_id}': {ee}")
                
        return {"exported_documents": len(documents), "files_generated": exported_files}
        
    except Exception as e:
        logger.error(f"Error during export stage: {e}")
        return {"error": str(e)}
    finally:
        if conn:
            conn.close()

def run_pipeline_all(domain: str = None, input_pdf: str = None) -> dict:
    """
    Runs all pipeline stages end-to-end (Init -> Split -> Extract -> Validate -> Transform -> Export).
    """
    logger.info("=========================================================")
    logger.info("  Running Full Pipeline End-to-End")
    logger.info("=========================================================")
    
    init_ok = run_init()
    if not init_ok:
        return {"success": False, "stage_failed": "init"}
        
    split_res = run_split_and_match(domain, input_pdf)
    extract_res = run_extract(domain)
    validate_res = run_validate(domain)
    transform_res = run_transform_to_db(domain)
    export_res = run_export_outputs(domain)
    
    return {
        "success": True,
        "split": split_res,
        "extract": extract_res,
        "validate": validate_res,
        "transform": transform_res,
        "export": export_res
    }

def reset_pipeline_data(domain: str = None, clear_storage_temp: bool = True, clear_database: bool = True) -> dict:
    """
    Resets the pipeline for a fresh interactive test run.
    - Clears transactional document database tables if clear_database is True.
    - Cleans temporary files in 02_split_pages and 03_processing_queue if clear_storage_temp is True.
    """
    setup_logger()
    logger.info("=========================================================")
    logger.info("  Resetting Pipeline Data (Fresh Start)")
    logger.info("=========================================================")
    
    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    if domain is None:
        domain = get_default_domain()
        
    res = {"database_reset": False, "storage_cleaned": False, "deleted_files_count": 0}
    
    # 1. Reset Database
    if clear_database:
        db_res = reset_pipeline_database(clear_documents_only=True)
        res["database_reset"] = db_res.get("success", False)
        
    # 2. Clean temporary pipeline storage
    if clear_storage_temp:
        domain_storage = os.path.join(storage_root, domain).replace("\\", "/")
        folders_to_clean = [
            os.path.join(domain_storage, "02_split_pages"),
            os.path.join(domain_storage, "03_processing_queue")
        ]
        
        deleted_count = 0
        for folder in folders_to_clean:
            if os.path.exists(folder):
                for root_dir, _, files in os.walk(folder):
                    for file in files:
                        if not file.startswith(".gitkeep"):
                            try:
                                os.remove(os.path.join(root_dir, file))
                                deleted_count += 1
                            except Exception as fe:
                                logger.warning(f"Could not remove temporary file {file}: {fe}")
                                
        res["storage_cleaned"] = True
        res["deleted_files_count"] = deleted_count
        logger.info(f"Cleaned {deleted_count} temporary files from 02_split_pages and 03_processing_queue.")
        
    return res

# Backward compatibility helper
def process_document(file_path: str, domain: str, template_name: str = "google_sheet_summary", 
                     export_format: str = "csv", settings: dict = None) -> dict | None:
    """
    Legacy helper: Single document direct processing.
    """
    if settings is None:
        settings = load_system_settings()
    res = run_pipeline_all(domain, file_path)
    return res if res.get("success") else None

