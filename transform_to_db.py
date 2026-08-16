import os
import json
import uuid
import sqlite3
from dotenv import load_dotenv
from loguru import logger
from src.core.db import (
    get_db_connection,
    create_document,
    insert_relational_receipt
)
from src.core.config_loader import load_system_settings
from src.core.logger import setup_logger

def main():
    setup_logger()
    logger.info("==========================================")
    logger.info("  Run_04_Transform_To_DB: DB Transformation")
    logger.info("==========================================")
    
    load_dotenv()
    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    domain = "expense_receipt" # default domain
    domain_storage = os.path.join(storage_root, domain)
    
    queue_dir = os.path.join(domain_storage, "03_processing_queue")
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Fetch pages that have status_code 'EXTRACTED'
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
            logger.info("No extracted pages (status: EXTRACTED) found for DB transformation.")
            return
            
        logger.info(f"Found {len(pages)} page(s) to import into DB relational tables...")
        
        successfully_imported_count = 0
        failed_imported_count = 0
        
        for p in pages:
            page_id = p["page_id"]
            batch_id = p["batch_id"]
            page_number = p["page_number"]
            image_path = p["image_path"]
            pdf_name = p["original_pdf_name"]
            storage_path = p["storage_path"]
            
            # Resolve matched source from storage path
            folder_name = os.path.basename(storage_path)
            source = "_default" if folder_name == "_uncategorized" else folder_name
            
            # Resolve JSON filename and path
            image_basename = os.path.splitext(os.path.basename(image_path))[0]
            json_filename = f"{image_basename}.json"
            json_filepath = os.path.join(queue_dir, source, json_filename).replace("\\", "/")
            
            if not os.path.exists(json_filepath):
                logger.error(f"Extracted JSON file not found on disk: {json_filepath}")
                # Update status of this page to FAILED due to missing JSON
                update_conn = get_db_connection()
                update_cursor = update_conn.cursor()
                update_cursor.execute("""
                    UPDATE document_pages
                    SET status_code = 'FAILED', error_reason = 'Extracted JSON file not found on disk.'
                    WHERE page_id = ?
                """, (page_id,))
                update_conn.commit()
                update_conn.close()
                failed_imported_count += 1
                continue
            
            # Load JSON data
            try:
                with open(json_filepath, "r", encoding="utf-8") as jf:
                    payload = json.load(jf)
            except Exception as read_err:
                logger.error(f"Failed to read/parse JSON file '{json_filename}': {read_err}")
                update_conn = get_db_connection()
                update_cursor = update_conn.cursor()
                update_cursor.execute("""
                    UPDATE document_pages
                    SET status_code = 'FAILED', error_reason = ?
                    WHERE page_id = ?
                """, (f"JSON Read Error: {str(read_err)}", page_id))
                update_conn.commit()
                update_conn.close()
                failed_imported_count += 1
                continue
                
            # Extract fields
            meta = payload.get("_metadata", {})
            model_used = meta.get("model_used")
            input_tokens = meta.get("input_tokens", 0)
            output_tokens = meta.get("output_tokens", 0)
            
            doc_number = payload.get("doc_number", "")
            doc_date = payload.get("transaction_date", "")
            entity_name = payload.get("merchant_name", "")
            
            fin_summary = payload.get("financial_summary", {})
            total_amount = fin_summary.get("net_amount", 0.0)
            
            tax_id = payload.get("tax_id", "")
            payment_method = payload.get("payment_method", "")
            search_text = f"{doc_number} {entity_name} {tax_id} {payment_method}".strip()
            
            # Evaluate scans validation
            val_meta = payload.get("validation_meta", {})
            is_complete = val_meta.get("is_complete", True)
            missing = val_meta.get("missing_pages", [])
            
            status_code = "PROCESSED"
            error_reason = None
            if not is_complete:
                status_code = "FAILED"
                error_reason = f"เอกสารสแกนมาไม่ครบถ้วน: ขาดหน้า {', '.join(map(str, missing))}"
                
            # Generate unique document ID for this page
            doc_id = f"doc_{uuid.uuid4().hex[:12]}"
            
            # Write to Database page-by-page
            update_conn = get_db_connection()
            try:
                # 1. Insert into documents
                create_document(
                    document_id=doc_id,
                    batch_id=batch_id,
                    domain_id=domain,
                    source_id=source,
                    status_code=status_code,
                    doc_number=doc_number,
                    doc_date=doc_date,
                    entity_name=entity_name,
                    total_amount=total_amount,
                    search_text=search_text,
                    data_payload=json.dumps(payload, ensure_ascii=False),
                    error_reason=error_reason,
                    model_used=model_used,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    conn=update_conn
                )
                
                # 2. Insert relational receipt
                if status_code == "PROCESSED":
                    insert_relational_receipt(doc_id, payload, pdf_name, conn=update_conn)
                    
                # 3. Update page link and status in document_pages
                update_cursor = update_conn.cursor()
                update_cursor.execute("""
                    UPDATE document_pages
                    SET document_id = ?, status_code = ?, error_reason = ?
                    WHERE page_id = ?
                """, (doc_id, status_code, error_reason, page_id))
                
                update_conn.commit()
                successfully_imported_count += 1
            except Exception as write_err:
                update_conn.rollback()
                logger.error(f"Failed to write relational data for page '{page_number}': {write_err}")
                failed_imported_count += 1
                # Mark page as failed in a separate transaction
                fail_conn = get_db_connection()
                fail_cursor = fail_conn.cursor()
                fail_cursor.execute("""
                    UPDATE document_pages
                    SET status_code = 'FAILED', error_reason = ?
                    WHERE page_id = ?
                """, (f"DB Write Error: {str(write_err)}", page_id))
                fail_conn.commit()
                fail_conn.close()
            finally:
                update_conn.close()
                
            logger.info(f"Imported Page {page_number} -> Relational DB (Status: {status_code})")
            
        logger.info("==========================================")
        logger.info("  Step 4: DB Transformation Summary")
        logger.info("==========================================")
        logger.info(f"Successfully imported: {successfully_imported_count}")
        logger.info(f"Failed to import: {failed_imported_count}")
        logger.info("==========================================")
        
    except Exception as e:
        logger.error(f"Error during DB transformation execution: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
