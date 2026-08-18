import os
import json
import uuid
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from loguru import logger
from src.core.db import (
    get_db_connection,
    create_document,
    link_pages_to_document,
    update_document_to_failed,
    insert_relational_receipt
)
from src.core.extractor import extract_document_data
from src.core.config_loader import load_system_settings, load_source_ai_config
from src.core.logger import setup_logger
from src.core.post_processor import apply_source_rules
from main import merge_chunk_payloads

def process_batch_extraction(b: dict, source: str, max_images: int, domain: str, queue_dir: str) -> tuple[bool, int]:
    """
    Processes the extraction for a single batch of images.
    Returns: (success: bool, docs_count: int)
    """
    batch_id = b["batch_id"]
    pdf_name = b["original_pdf_name"]
    
    # Fetch pending split page image paths using a temporary connection
    temp_conn = get_db_connection()
    temp_cursor = temp_conn.cursor()
    temp_cursor.execute("""
        SELECT image_path, page_number FROM document_pages
        WHERE batch_id = ? AND status_code IN ('PREPROCESSED', 'FAILED', 'PENDING')
        ORDER BY page_number ASC
    """, (batch_id,))
    pages = temp_cursor.fetchall()
    temp_conn.close()
    
    if not pages:
        return True, 0
        
    logger.info(f"Extracting Batch: {pdf_name} (ID: {batch_id}) | Source: {source} | Pending Pages: {len(pages)}")
    
    image_paths = [p["image_path"] for p in pages]
    payloads = []
    extraction_success = True
    err_msg = ""
    
    # Call Gemini extraction engine (Auto-Chunking)
    if len(image_paths) <= max_images:
        logger.info(f"Processing all {len(image_paths)} pages of batch {batch_id} in a single Request...")
        try:
            page_data = extract_document_data(image_paths, source, domain, batch_id=batch_id, chunk_index=1)
            payloads.append(page_data)
        except Exception as e:
            logger.error(f"Structured extraction failed for batch {batch_id}: {e}")
            extraction_success = False
            err_msg = f"Gemini Extraction Exception: {str(e)}"
    else:
        # Page count > max limit, slice into chunks
        chunks = [image_paths[i:i + max_images] for i in range(0, len(image_paths), max_images)]
        logger.info(f"Page count ({len(image_paths)}) for batch {batch_id} exceeds limit ({max_images}). Split into {len(chunks)} Requests...")
        
        for idx, chunk in enumerate(chunks):
            logger.info(f"Sending Part {idx + 1} of {len(chunks)} (pages {idx*max_images + 1} to {idx*max_images + len(chunk)}) for batch {batch_id}...")
            try:
                part_data = extract_document_data(chunk, source, domain, batch_id=batch_id, chunk_index=idx + 1)
                payloads.append(part_data)
            except Exception as e:
                logger.error(f"Part {idx + 1} extraction failed for batch {batch_id}: {e}")
                extraction_success = False
                err_msg = f"Part {idx + 1} Gemini Extraction Exception: {str(e)}"
                break
                
    # Handle persistent updates page-by-page on failure
    if not extraction_success:
        # Mark all pending pages in this batch as FAILED
        for p in pages:
            p_num = p["page_number"]
            update_conn = get_db_connection()
            update_cursor = update_conn.cursor()
            update_cursor.execute("""
                UPDATE document_pages
                SET status_code = 'FAILED', error_reason = ?
                WHERE batch_id = ? AND page_number = ?
            """, (err_msg, batch_id, p_num))
            update_conn.commit()
            update_conn.close()
        return False, 0
        
    docs_count = 0
    try:
        # Process extracted documents list
        all_docs = []
        model_used = None
        total_input_tokens = 0
        total_output_tokens = 0
        
        for p_load in payloads:
            meta = p_load.get("_metadata", {})
            if meta:
                model_used = meta.get("model_used")
                total_input_tokens += meta.get("input_tokens", 0)
                total_output_tokens += meta.get("output_tokens", 0)
            
            docs_in_payload = p_load.get("extracted_documents", [])
            all_docs.extend(docs_in_payload)
        
        if not all_docs:
            logger.warning(f"AI returned empty extracted documents list for batch {batch_id}. Marking batch pages as FAILED.")
            for p in pages:
                p_num = p["page_number"]
                update_conn = get_db_connection()
                update_cursor = update_conn.cursor()
                update_cursor.execute("""
                    UPDATE document_pages
                    SET status_code = 'FAILED', error_reason = 'AI returned no extracted documents.'
                    WHERE batch_id = ? AND page_number = ?
                """, (batch_id, p_num))
                update_conn.commit()
                update_conn.close()
            return False, 0
            
        # Attribute tokens per page/document
        doc_count = len(all_docs)
        input_tokens_per_doc = int(total_input_tokens / doc_count)
        output_tokens_per_doc = int(total_output_tokens / doc_count)
        
        # Fetch all pages for this batch for lookup
        lookup_conn = get_db_connection()
        lookup_cursor = lookup_conn.cursor()
        lookup_cursor.execute("SELECT page_id, page_number, image_path FROM document_pages WHERE batch_id = ?", (batch_id,))
        db_pages = {p["page_number"]: {"page_id": p["page_id"], "image_path": p["image_path"]} for p in lookup_cursor.fetchall()}
        lookup_conn.close()
        
        # Ensure source directory exists in 03_processing_queue
        source_queue_dir = os.path.join(queue_dir, source)
        os.makedirs(source_queue_dir, exist_ok=True)
        
        for doc_payload in all_docs:
            logical_page = doc_payload.get("logical_page_number", 1)
            
            page_info = db_pages.get(logical_page)
            if not page_info:
                logger.warning(f"Logical page number {logical_page} not found in database for batch {batch_id}. Skipping.")
                continue
                
            image_path = page_info["image_path"]
            image_basename = os.path.splitext(os.path.basename(image_path))[0]
            
            # Inject token usage metadata
            doc_payload["_metadata"] = {
                "model_used": model_used,
                "input_tokens": input_tokens_per_doc,
                "output_tokens": output_tokens_per_doc
            }
            
            # Write to JSON file
            json_filename = f"{image_basename}.json"
            json_filepath = os.path.join(source_queue_dir, json_filename).replace("\\", "/")
            
            with open(json_filepath, "w", encoding="utf-8") as jf:
                json.dump(doc_payload, jf, ensure_ascii=False, indent=2)
                
            # Evaluate validation metadata for this page
            val_meta = doc_payload.get("validation_meta", {})
            is_complete = val_meta.get("is_complete", True)
            missing = val_meta.get("missing_pages", [])
            
            status_code = "EXTRACTED"
            error_reason = None
            if not is_complete:
                status_code = "FAILED"
                error_reason = f"เอกสารสแกนมาไม่ครบถ้วน: ขาดหน้า {', '.join(map(str, missing))}"
                logger.error(f"Scan validation error for logical page {logical_page} in batch {batch_id}: {error_reason}")
            
            # Update status of this page in database page-by-page
            update_conn = get_db_connection()
            update_cursor = update_conn.cursor()
            update_cursor.execute("""
                UPDATE document_pages
                SET status_code = ?, error_reason = ?
                WHERE batch_id = ? AND page_number = ?
            """, (status_code, error_reason, batch_id, logical_page))
            update_conn.commit()
            update_conn.close()
            
            logger.info(f"Registered Page {logical_page} of batch {batch_id} -> JSON Exported: {json_filename} (Status: {status_code})")
            docs_count += 1
            
    except Exception as loop_e:
        logger.error(f"Error during JSON payload file write for batch {batch_id}: {loop_e}")
        return False, 0
        
    return True, docs_count

def main():
    setup_logger()
    logger.info("==========================================")
    logger.info("  Run_03_Extract_Data: Structured Data Extraction")
    logger.info("==========================================")
    
    load_dotenv()
    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    domain = "expense_receipt" # default domain
    domain_storage = os.path.join(storage_root, domain)
    
    queue_dir = os.path.join(domain_storage, "03_processing_queue")
    os.makedirs(queue_dir, exist_ok=True)
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Fetch batches that have pages needing extraction
        cursor.execute("""
            SELECT DISTINCT pb.batch_id, pb.original_pdf_name, pb.storage_path
            FROM processed_batches pb
            JOIN document_pages dp ON pb.batch_id = dp.batch_id
            WHERE dp.status_code IN ('PREPROCESSED', 'FAILED', 'PENDING')
        """)
        batches = cursor.fetchall()
        conn.close()
        conn = None
        
        if not batches:
            logger.info("No pending batches requiring AI data extraction.")
            return
            
        logger.info(f"Found {len(batches)} batch(es) containing pending/failed pages to process...")
        
        max_images = settings.get("max_images_per_request", 50)
        concurrency_cfg = settings.get("concurrency", {})
        default_workers = concurrency_cfg.get("default", 4)
        model_workers_cfg = concurrency_cfg.get("models", {})
        
        # Group batches by their resolved AI model name
        batches_by_model = {}
        for b in batches:
            storage_path = b["storage_path"]
            folder_name = os.path.basename(storage_path)
            source = "_default" if folder_name == "_uncategorized" else folder_name
            
            # Resolve AI provider and model name for this source
            _, model_name = load_source_ai_config(domain, source, settings)
            if model_name not in batches_by_model:
                batches_by_model[model_name] = []
            batches_by_model[model_name].append((b, source))
            
        successfully_extracted_docs_count = 0
        failed_batches_count = 0
        total_batches_processed = 0
        
        # Run thread pools separately for each model to respect concurrency limits
        for model_name, batch_list in batches_by_model.items():
            max_workers = model_workers_cfg.get(model_name, default_workers)
            logger.info(f"Starting ThreadPoolExecutor for model '{model_name}' with max_workers={max_workers} (Processing {len(batch_list)} batches)...")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        process_batch_extraction,
                        b=item[0],
                        source=item[1],
                        max_images=max_images,
                        domain=domain,
                        queue_dir=queue_dir
                    ): item[0]["original_pdf_name"]
                    for item in batch_list
                }
                
                for future in as_completed(futures):
                    pdf_name = futures[future]
                    try:
                        success, docs_count = future.result()
                        total_batches_processed += 1
                        if success:
                            successfully_extracted_docs_count += docs_count
                        else:
                            failed_batches_count += 1
                    except Exception as e:
                        logger.error(f"Part {idx + 1} extraction failed: {e}")
                        extraction_success = False
                        err_msg = f"Part {idx + 1} Gemini Extraction Exception: {str(e)}"
                        break
            
            # 3. Handle persistent updates page-by-page
            if not extraction_success:
                # Mark all pending pages in this batch as FAILED
                for p in pages:
                    p_num = p["page_number"]
                    update_conn = get_db_connection()
                    update_cursor = update_conn.cursor()
                    update_cursor.execute("""
                        UPDATE document_pages
                        SET status_code = 'FAILED', error_reason = ?
                        WHERE batch_id = ? AND page_number = ?
                    """, (err_msg, batch_id, p_num))
                    update_conn.commit()
                    update_conn.close()
                failed_batches_count += 1
                continue
                
            try:
                # Process extracted documents list
                all_docs = []
                model_used = None
                total_input_tokens = 0
                total_output_tokens = 0
                
                for p_load in payloads:
                    meta = p_load.get("_metadata", {})
                    if meta:
                        model_used = meta.get("model_used")
                        total_input_tokens += meta.get("input_tokens", 0)
                        total_output_tokens += meta.get("output_tokens", 0)
                    
                    docs_in_payload = p_load.get("extracted_documents", [])
                    all_docs.extend(docs_in_payload)
                
                if not all_docs:
                    logger.warning("AI returned empty extracted documents list. Marking batch pages as FAILED.")
                    for p in pages:
                        p_num = p["page_number"]
                        update_conn = get_db_connection()
                        update_cursor = update_conn.cursor()
                        update_cursor.execute("""
                            UPDATE document_pages
                            SET status_code = 'FAILED', error_reason = 'AI returned no extracted documents.'
                            WHERE batch_id = ? AND page_number = ?
                        """, (batch_id, p_num))
                        update_conn.commit()
                        update_conn.close()
                    failed_batches_count += 1
                    continue
                    
                # Attribute tokens per page/document
                doc_count = len(all_docs)
                input_tokens_per_doc = int(total_input_tokens / doc_count)
                output_tokens_per_doc = int(total_output_tokens / doc_count)
                
                # Fetch all pages for this batch for lookup
                lookup_conn = get_db_connection()
                lookup_cursor = lookup_conn.cursor()
                lookup_cursor.execute("SELECT page_id, page_number, image_path FROM document_pages WHERE batch_id = ?", (batch_id,))
                db_pages = {p["page_number"]: {"page_id": p["page_id"], "image_path": p["image_path"]} for p in lookup_cursor.fetchall()}
                lookup_conn.close()
                
                # Ensure source directory exists in 03_processing_queue
                source_queue_dir = os.path.join(queue_dir, source)
                os.makedirs(source_queue_dir, exist_ok=True)
                
                for doc_payload in all_docs:
                    # Apply source-specific post-processing rules
                    doc_payload, requires_review, review_reason = apply_source_rules(doc_payload, domain, source)

                    logical_page = doc_payload.get("logical_page_number", 1)
                    
                    page_info = db_pages.get(logical_page)
                    if not page_info:
                        logger.warning(f"Logical page number {logical_page} not found in database. Skipping.")
                        continue
                        
                    image_path = page_info["image_path"]
                    image_basename = os.path.splitext(os.path.basename(image_path))[0]
                    
                    # Inject token usage metadata
                    doc_payload["_metadata"] = {
                        "model_used": model_used,
                        "input_tokens": input_tokens_per_doc,
                        "output_tokens": output_tokens_per_doc
                    }
                    
                    # Write to JSON file
                    json_filename = f"{image_basename}.json"
                    json_filepath = os.path.join(source_queue_dir, json_filename).replace("\\", "/")
                    
                    with open(json_filepath, "w", encoding="utf-8") as jf:
                        json.dump(doc_payload, jf, ensure_ascii=False, indent=2)
                        
                    # Evaluate validation metadata for this page
                    val_meta = doc_payload.get("validation_meta", {})
                    is_complete = val_meta.get("is_complete", True)
                    missing = val_meta.get("missing_pages", [])
                    
                    post_meta = doc_payload.get("_post_processing_meta", {})
                    requires_review = post_meta.get("requires_review", False)
                    review_reasons = post_meta.get("review_reasons", [])
                    
                    status_code = "EXTRACTED"
                    error_reason = None
                    if not is_complete:
                        status_code = "FAILED"
                        error_reason = f"เอกสารสแกนมาไม่ครบถ้วน: ขาดหน้า {', '.join(map(str, missing))}"
                        logger.error(f"Scan validation error for logical page {logical_page}: {error_reason}")
                    elif requires_review:
                        status_code = "NEEDS_REVIEW"
                        error_reason = " | ".join(review_reasons)
                        logger.warning(f"Rule validation flags review for logical page {logical_page}: {error_reason}")
                    
                    # Update status of this page in database page-by-page
                    update_conn = get_db_connection()
                    update_cursor = update_conn.cursor()
                    update_cursor.execute("""
                        UPDATE document_pages
                        SET status_code = ?, error_reason = ?
                        WHERE batch_id = ? AND page_number = ?
                    """, (status_code, error_reason, batch_id, logical_page))
                    update_conn.commit()
                    update_conn.close()
                    
                    logger.info(f"Registered Page {logical_page} -> JSON Exported: {json_filename} (Status: {status_code})")
                    successfully_extracted_docs_count += 1
                
            except Exception as loop_e:
                logger.error(f"Error during JSON payload file write: {loop_e}")
                raise loop_e
            
            total_batches_processed += 1
        logger.info("==========================================")
        logger.info("  Step 3: AI Data Extraction Summary")
        logger.info("==========================================")
        logger.info(f"Total batches processed: {total_batches_processed}")
        logger.info(f"Successfully extracted and saved JSONs: {successfully_extracted_docs_count}")
        logger.info(f"Failed or skipped batches: {failed_batches_count}")
        logger.info("==========================================")
    except Exception as e:
        logger.error(f"Error during data extraction execution: {e}")
    finally:
        pass

if __name__ == "__main__":
    main()
