import os
import sys
import json
import argparse
import shutil
import pandas as pd
from dotenv import load_dotenv
from loguru import logger

# Import core engine modules
from src.core.pdf_splitter import split_pdf
from src.core.source_matcher import match_source
from src.core.extractor import extract_receipt_data
from src.core.transformer import transform_data
from src.core.initializer import (
    validate_settings_config,
    validate_domain_config,
    initialize_storage_directories
)
from src.core.logger import setup_logger
from src.core.database import (
    calculate_file_hash,
    check_duplicate_document,
    insert_pending_document
)

def process_document(file_path: str, domain: str, template_name: str, export_format: str, settings: dict):
    """
    Orchestrates the end-to-end processing pipeline for a single document (PDF or Image).
    """
    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        logger.warning("GEMINI_API_KEY is not set in the environment variables.")
        logger.warning("Please check your .env file or export the API key before running.")
        
    # Get configuration paths
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
    
    # Calculate SHA-256 and validate duplicate document
    try:
        file_hash = calculate_file_hash(file_path)
        is_dup, dup_meta = check_duplicate_document(file_hash)
        if is_dup:
            if dup_meta['status'] == 'archived':
                logger.error(f"Duplicate document detected! File hash: {file_hash}")
                logger.error(f"This file has already been processed and archived in domain '{dup_meta['domain']}' on {dup_meta['processed_at']}.")
                logger.error("Processing aborted.")
                return
            else:
                logger.warning(f"Document already exists in the processing queue (status: '{dup_meta['status']}')")
    except Exception as he:
        logger.error(f"Failed to perform duplicate check: {he}")
        return
        
    logger.info("=========================================================")
    logger.info(f"Processing File: {file_path}")
    logger.info(f"Domain: {domain} | Template: {template_name} | Format: {export_format}")
    logger.info("=========================================================")
    
    # 1. Page Splitting & Image Generation
    image_paths = []
    first_page_image = None
    
    if file_lower.endswith(".pdf"):
        logger.info("[STEP 1/4] Splitting PDF into page images...")
        try:
            image_paths = split_pdf(file_path, split_dir)
            if image_paths:
                first_page_image = image_paths[0]
        except Exception as e:
            logger.error(f"Failed to split PDF: {e}")
            return
    elif file_lower.endswith((".png", ".jpg", ".jpeg")):
        logger.info("[STEP 1/4] Input is an image. Skipping PDF splitting.")
        image_paths = [file_path]
    else:
        logger.error(f"Unsupported file format: {file_path}")
        return
        
    # 2. Source Matching & Categorization (Flat Staging Flow)
    inbox_dir = os.path.abspath(os.path.join(domain_storage, "01_raw_inbox")).replace("\\", "/")
    file_parent_dir = os.path.abspath(os.path.dirname(file_path)).replace("\\", "/")
    
    # Check if the file is already in a subfolder inside 01_raw_inbox/
    if os.path.dirname(file_parent_dir) == inbox_dir:
        folder_name = os.path.basename(file_parent_dir)
        source = "_default" if folder_name == "_uncategorized" else folder_name
        logger.info(f"[SKIP MATCHING] File is pre-categorized as source '{source}' (Path: {file_path})")
    else:
        logger.info("[STEP 2/4] Matching document source...")
        source = match_source(file_path, domain, first_page_image)
        logger.info(f"Matched source: '{source}'")
        
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
        
    # Rename split page PNG images to match the config-driven format:
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
        
        if file_lower.endswith(".pdf"):
            if os.path.exists(old_path):
                if os.path.exists(new_path):
                    os.remove(new_path)
                os.rename(old_path, new_path)
            renamed_image_paths.append(new_path)
        else:
            # If it's a raw image, copy/save it to split_dir with the official name
            shutil.copy(old_path, new_path)
            renamed_image_paths.append(new_path)
            
    image_paths = renamed_image_paths
    
    # Record document as in_progress in SQLite DB
    try:
        insert_pending_document(file_hash, domain, os.path.basename(file_path), source)
    except Exception as ie:
        logger.warning(f"Failed to record pending document state in database: {ie}")
        
    # 3. Data Extraction (Page-by-Page)
    logger.info("[STEP 3/4] Extracting structured data from pages...")
    extracted_pages = []
    
    for i, img_path in enumerate(image_paths):
        page_num = i + 1
        logger.info(f"Processing Page {page_num} of {len(image_paths)}...")
        try:
            # Extract structured JSON using Gemini API
            page_data = extract_receipt_data(img_path, source, domain)
            
            # Save extracted JSON in the processing queue
            new_json_base = filename_pattern.replace("{domain}", domain)\
                                            .replace("{source}", source)\
                                            .replace("{doc_no}", base_filename)\
                                            .replace("{page_no}", f"{page_num:03d}")
            json_filename = f"{new_json_base}.json"
            queue_json_path = os.path.join(queue_dir, json_filename)
            
            with open(queue_json_path, "w", encoding="utf-8") as f:
                json.dump(page_data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Saved raw JSON to queue: {queue_json_path}")
            extracted_pages.append(page_data)
        except Exception as e:
            logger.error(f"Failed to extract page {page_num}: {e}")
            
    if not extracted_pages:
        logger.error("No data extracted from document.")
        return
        
    # 4. Transformation
    logger.info("[STEP 4/4] Transforming and flattening extracted data...")
    all_flattened_rows = []
    
    for page_data in extracted_pages:
        try:
            rows = transform_data(page_data, template_path)
            all_flattened_rows.extend(rows)
        except Exception as e:
            logger.error(f"Failed to transform data: {e}")
            
    if not all_flattened_rows:
        logger.warning("Transformation produced 0 rows.")
        return
        
    # Export results
    os.makedirs("outputs", exist_ok=True)
    df = pd.DataFrame(all_flattened_rows)
    
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
    logger.info("---------------------------------")
    logger.info(f"\n{df.to_string()}")
    logger.info("---------------------------------")

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
    try:
        with open(args.settings, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception as e:
        logger.critical(f"Failed to load settings: {e}")
        sys.exit(1)
        
    # Run the document pipeline
    process_document(args.input, args.domain, args.template, args.format, settings)
