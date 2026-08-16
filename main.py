import os
import sys
import json
import argparse
import shutil
import uuid
import copy
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

# Import core engine modules
from src.core.pdf_splitter import split_pdf
from src.core.source_matcher import match_source
from src.core.extractor import extract_document_data
from src.core.transformer import transform_data
from src.core.initializer import (
    validate_settings_config,
    validate_domain_config,
    initialize_storage_directories
)
from src.core.logger import setup_logger
from src.core.config_loader import is_domain_active, is_source_active, load_system_settings
from src.core.db import (
    calculate_file_hash,
    check_duplicate_document,
    create_batch,
    create_page,
    create_document,
    link_pages_to_document,
    update_document_payload,
    update_document_to_failed,
    insert_relational_receipt
)

def merge_chunk_payloads(payloads: list[dict]) -> dict:
    """
    Merges multiple extracted JSON payloads from different requests of the same batch.
    - Header info from the first part.
    - Items concatenated from all parts.
    - Financial Summary from the final part.
    - validation_meta combined logically.
    """
    if not payloads:
        return {}
    
    first = payloads[0]
    final = payloads[-1]
    
    # Clone structure from the first payload
    merged = copy.deepcopy(first)
    
    # 1. Merge all items
    all_items = []
    for p in payloads:
        all_items.extend(p.get("items", []))
    merged["items"] = all_items
    
    # 2. Use financial summary from the final part
    merged["financial_summary"] = final.get("financial_summary", {
        "subtotal": 0.0,
        "discount": 0.0,
        "vat_amount": 0.0,
        "net_amount": 0.0
    })
    
    # 3. Merge validation meta
    is_complete = True
    missing_pages = []
    logical_page_order = []
    
    current_page_offset = 0
    for p in payloads:
        meta = p.get("validation_meta", {})
        if not meta.get("is_complete", True):
            is_complete = False
            missing_pages.extend(meta.get("missing_pages", []))
            
        part_order = meta.get("logical_page_order", [])
        offset_order = [idx + current_page_offset for idx in part_order]
        logical_page_order.extend(offset_order)
        
        # Increment offset based on logical pages read in this request, fallback to 50 if empty
        current_page_offset += len(part_order) if part_order else 50
        
    merged["validation_meta"] = {
        "is_complete": is_complete,
        "missing_pages": sorted(list(set(missing_pages))),
        "logical_page_order": logical_page_order
    }
    
    return merged

def process_document(file_path: str, domain: str, template_name: str, export_format: str, settings: dict):
    """
    Orchestrates the end-to-end processing pipeline for a single document (PDF or Image).
    Implements file boundaries, duplicate checks, auto-chunking, and auto-merging.
    """
    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        logger.warning("GEMINI_API_KEY is not set in the environment variables.")
        logger.warning("Please check your .env file or export the API key before running.")
        
    # Check if domain is active in database and configurations
    if not is_domain_active(domain):
        logger.error(f"Domain '{domain}' is not active or not configured in system.")
        return
        
    storage_root = settings.get("storage_root", "pipeline_storage")
    domain_storage = os.path.join(storage_root, domain)
    
    split_dir = os.path.join(domain_storage, "02_split_pages")
    queue_dir = os.path.join(domain_storage, "03_processing_queue")
    
    # Resolve the template config path
    template_path = f"configs/domains/{domain}/outputs/{template_name}.json"
    if not os.path.exists(template_path):
        logger.error(f"Specified template not found: {template_path}")
        return
        
    file_path = os.path.abspath(file_path).replace("\\", "/")
    base_filename = os.path.splitext(os.path.basename(file_path))[0]
    file_lower = file_path.lower()
    
    # 1. Calculate SHA-256 and validate duplicate document
    try:
        file_hash = calculate_file_hash(file_path)
        is_dup, dup_meta = check_duplicate_document(file_hash)
        if is_dup:
            if dup_meta['status'] == 'APPROVED':
                logger.error(f"Duplicate document detected! File hash: {file_hash}")
                logger.error(f"This file has already been approved and locked in domain '{dup_meta['domain']}' on {dup_meta['created_at']}.")
                logger.error("Processing aborted to prevent overwriting approved records.")
                return
            else:
                logger.warning(f"Document already exists in the database queue (status: '{dup_meta['status']}')")
    except Exception as he:
        logger.error(f"Failed to perform duplicate check: {he}")
        return
        
    logger.info("=========================================================")
    logger.info(f"Processing File: {file_path}")
    logger.info(f"Domain: {domain} | Template: {template_name} | Format: {export_format}")
    logger.info("=========================================================")
    
    # 2. Split PDF/Image into page images
    image_paths = []
    first_page_image = None
    
    if file_lower.endswith(".pdf"):
        logger.info("[STEP 1/5] Splitting PDF into page images...")
        try:
            image_paths = split_pdf(file_path, split_dir)
            if image_paths:
                first_page_image = image_paths[0]
        except Exception as e:
            logger.error(f"Failed to split PDF: {e}")
            return
    elif file_lower.endswith((".png", ".jpg", ".jpeg")):
        logger.info("[STEP 1/5] Input is an image. Skipping PDF splitting.")
        # Save copy to split directory to have a managed copy
        image_name = f"temp_{base_filename}.png"
        dest_split_path = os.path.join(split_dir, image_name).replace("\\", "/")
        shutil.copy(file_path, dest_split_path)
        image_paths = [dest_split_path]
        first_page_image = dest_split_path
    else:
        logger.error(f"Unsupported file format: {file_path}")
        return

    # Generate unique IDs for Batch, Pages, and Document
    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    document_id = f"doc_{uuid.uuid4().hex[:12]}"
    
    # Register Batch in database
    logger.info(f"Registering batch '{batch_id}' in SQLite database...")
    create_batch(
        batch_id=batch_id,
        original_pdf_name=os.path.basename(file_path),
        total_pages=len(image_paths),
        storage_path=os.path.dirname(file_path),
        file_hash=file_hash
    )
    
    # Register pages in database as PENDING
    for idx, img_path in enumerate(image_paths):
        page_num = idx + 1
        page_id = f"page_{batch_id}_{page_num:03d}"
        create_page(
            page_id=page_id,
            batch_id=batch_id,
            page_number=page_num,
            image_path=img_path,
            status_code="PENDING"
        )
        
    # 3. Source Matching & Categorization (Strict boundary check)
    inbox_dir = os.path.abspath(os.path.join(domain_storage, "01_raw_inbox")).replace("\\", "/")
    file_parent_dir = os.path.abspath(os.path.dirname(file_path)).replace("\\", "/")
    
    # Check if the file is already inside 01_raw_inbox subfolder
    if os.path.dirname(file_parent_dir) == inbox_dir:
        folder_name = os.path.basename(file_parent_dir)
        source = "_default" if folder_name == "_uncategorized" else folder_name
        logger.info(f"[SKIP MATCHING] File is pre-categorized as source '{source}' (Path: {file_path})")
    else:
        logger.info("[STEP 2/5] Matching document source...")
        source = match_source(file_path, domain, first_page_image)
        logger.info(f"Matched source: '{source}'")
        
        # Check active status of source in SQLite
        if not is_source_active(domain, source):
            logger.warning(f"Source '{source}' is currently deactivated in settings. Falling back to default source.")
            source = "_default"
            
        # Categorize the file under 01_raw_inbox
        os.makedirs(inbox_dir, exist_ok=True)
        if source == "_default":
            dest_folder = os.path.join(inbox_dir, "_uncategorized")
        else:
            dest_folder = os.path.join(inbox_dir, source)
            
        os.makedirs(dest_folder, exist_ok=True)
        dest_path = os.path.join(dest_folder, os.path.basename(file_path)).replace("\\", "/")
        
        if file_path != dest_path:
            shutil.move(file_path, dest_path)
            logger.info(f"Moved raw file to categorized folder: {dest_path}")
        file_path = dest_path

    # Rename split page PNG images to match system naming pattern
    archiving_cfg = settings.get("archiving", {})
    filename_pattern = archiving_cfg.get("filename_pattern", "{domain}_{source}_{doc_no}_{page_no}")
    
    renamed_image_paths = []
    for i, old_path in enumerate(image_paths):
        page_num = i + 1
        new_filename_base = filename_pattern.replace("{domain}", domain)\
                                            .replace("{source}", source)\
                                            .replace("{doc_no}", base_filename)\
                                            .replace("{page_no}", f"{page_num:03d}")
        new_filename = f"{new_filename_base}.png"
        new_path = os.path.join(split_dir, new_filename).replace("\\", "/")
        
        if os.path.exists(old_path):
            if os.path.exists(new_path):
                os.remove(new_path)
            os.rename(old_path, new_path)
            
        renamed_image_paths.append(new_path)
        
        # Update database with renamed path
        page_id = f"page_{batch_id}_{page_num:03d}"
        create_page(
            page_id=page_id,
            batch_id=batch_id,
            page_number=page_num,
            image_path=new_path,
            status_code="PROCESSED"
        )
            
    image_paths = renamed_image_paths
    
    # 4. Data Extraction using Auto-Chunking
    logger.info("[STEP 3/5] Extracting structured data from pages...")
    max_images = settings.get("max_images_per_request", 50)
    
    payloads = []
    
    # Perform chunked execution
    if len(image_paths) <= max_images:
        logger.info(f"Processing all {len(image_paths)} pages in a single API request.")
        try:
            page_data = extract_document_data(image_paths, source, domain)
            payloads.append(page_data)
        except Exception as e:
            logger.error(f"Structured extraction request failed: {e}")
            create_document(
                document_id=document_id,
                batch_id=batch_id,
                domain_id=domain,
                source_id=source,
                status_code="FAILED",
                error_reason=f"Gemini Extraction Exception: {str(e)}"
            )
            link_pages_to_document(batch_id, document_id)
            return
    else:
        # Split into chunks of size max_images
        chunks = [image_paths[i:i + max_images] for i in range(0, len(image_paths), max_images)]
        logger.info(f"Page count ({len(image_paths)}) exceeds limit ({max_images}). Split into {len(chunks)} API requests.")
        
        for idx, chunk in enumerate(chunks):
            logger.info(f"Processing Part {idx + 1} of {len(chunks)} (pages {idx*max_images + 1} to {idx*max_images + len(chunk)})...")
            try:
                part_data = extract_document_data(chunk, source, domain)
                payloads.append(part_data)
            except Exception as e:
                logger.error(f"Part {idx + 1} extraction failed: {e}")
                create_document(
                    document_id=document_id,
                    batch_id=batch_id,
                    domain_id=domain,
                    source_id=source,
                    status_code="FAILED",
                    error_reason=f"Part {idx + 1} Gemini Extraction Exception: {str(e)}"
                )
                link_pages_to_document(batch_id, document_id)
                return
                
    # 5. Auto-Merge extracted payloads
    logger.info("[STEP 4/5] Merging chunked outputs...")
    final_payload = merge_chunk_payloads(payloads)
    
    # Evaluate Validation Meta (Missing pages scan error check)
    validation_meta = final_payload.get("validation_meta", {})
    is_complete = validation_meta.get("is_complete", True)
    missing = validation_meta.get("missing_pages", [])
    
    status_code = "PROCESSED"
    error_reason = None
    
    if not is_complete:
        status_code = "FAILED"
        error_reason = f"เอกสารสแกนมาไม่ครบถ้วน: ขาดหน้า {', '.join(map(str, missing))}"
        logger.error(error_reason)
        
    # Extract DB representation fields
    doc_number = final_payload.get("doc_number", "")
    doc_date = final_payload.get("transaction_date", "")
    entity_name = final_payload.get("merchant_name", "")
    
    fin_summary = final_payload.get("financial_summary", {})
    total_amount = fin_summary.get("net_amount", 0.0)
    
    tax_id = final_payload.get("tax_id", "")
    payment_method = final_payload.get("payment_method", "")
    search_text = f"{doc_number} {entity_name} {tax_id} {payment_method}".strip()
    
    # Create Document record in SQLite
    create_document(
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
        data_payload=json.dumps(final_payload, ensure_ascii=False),
        error_reason=error_reason
    )
    
    # Link all page images to this document
    link_pages_to_document(batch_id, document_id)
    
    # Insert relational receipt details into SQLite
    if status_code == "PROCESSED":
        insert_relational_receipt(document_id, final_payload, os.path.basename(file_path))
        
    logger.info(f"Registered document record '{document_id}' (Status: {status_code}) in database.")
    
    if status_code == "FAILED":
        logger.warning("Pipeline completed with verification errors. Review required on Streamlit UI.")
        return
        
    # 6. Transform & Export
    logger.info("[STEP 5/5] Transforming and flattening extracted data...")
    try:
        rows = transform_data(final_payload, template_path)
        if rows:
            # Export results
            os.makedirs("outputs", exist_ok=True)
            df = pd.DataFrame(rows)
            
            output_filename = f"{domain}_{template_name}_export"
            output_base_path = os.path.join("outputs", output_filename)
            
            if export_format == "csv":
                output_file = f"{output_base_path}.csv"
                df.to_csv(output_file, index=False, encoding="utf-8-sig")
            else:
                output_file = f"{output_base_path}.json"
                df.to_json(output_file, orient="records", force_ascii=False, indent=2)
                
            logger.info("Pipeline execution finished successfully!")
            logger.info(f"Flattened data exported to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to transform data: {e}")
        update_document_to_failed(document_id, f"Transformation Error: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI-Multi-Docs-Extraction-Pipeline Core Engine CLI")
    parser.add_argument("--input", "-i", required=True, help="Path to input receipt PDF or image")
    parser.add_argument("--domain", "-d", default="expense_receipt", help="Domain config name (default: expense_receipt)")
    parser.add_argument("--template", "-t", default="google_sheet_summary", help="Conversion template name (default: google_sheet_summary)")
    parser.add_argument("--format", "-f", choices=["csv", "json"], default="csv", help="Export file format (default: csv)")
    parser.add_argument("--settings", "-s", default="configs/settings.json", help="Path to settings.json")
    
    args = parser.parse_args()
    
    # Initialize logger
    setup_logger(args.settings)
    
    # 1. Validate central settings
    settings_valid, settings_errors = validate_settings_config(args.settings)
    if not settings_valid:
        logger.critical("Central settings.json has validation errors:")
        for err in settings_errors:
            logger.critical(f"  - {err}")
        sys.exit(1)
        
    # 2. Validate selected domain configuration
    domain_valid, domain_errors = validate_domain_config(args.domain)
    if not domain_valid:
        logger.critical(f"Domain '{args.domain}' config has validation errors:")
        for err in domain_errors:
            logger.critical(f"  - {err}")
        sys.exit(1)
        
    # 3. Initialize storage folders
    initialize_storage_directories(args.settings)
    
    # Load settings for processing
    settings = load_system_settings(args.settings)
    if not settings:
        logger.critical("Failed to load settings configuration.")
        sys.exit(1)
        
    # Run the document pipeline
    process_document(args.input, args.domain, args.template, args.format, settings)
