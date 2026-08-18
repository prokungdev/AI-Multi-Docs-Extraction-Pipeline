import sys
import os
import json
import sqlite3

# Set Python path to ensure src can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.db import get_db_connection, insert_relational_receipt, create_document
from loguru import logger

def seed_from_queue():
    """
    Scans the 03_processing_queue folder for JSON payloads, matches them to 
    document_id in the database, and inserts them into relational tables.
    If the document record is missing, it automatically recreates it.
    """
    logger.info("Starting historical data migration from 03_processing_queue...")
    
    storage_root = "pipeline_storage"
    domain = "expense_receipt"
    queue_dir = os.path.join(storage_root, domain, "03_processing_queue")
    
    if not os.path.exists(queue_dir):
        logger.error(f"Processing queue folder not found: {queue_dir}")
        return
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        migrated_count = 0
        skipped_count = 0
        
        # Traverse directories to find JSON files
        for root, dirs, files in os.walk(queue_dir):
            for file in files:
                if file.endswith(".json") and file != ".gitkeep":
                    json_path = os.path.join(root, file)
                    image_basename = os.path.splitext(file)[0]
                    source = os.path.basename(root)
                    
                    # Read JSON payload
                    with open(json_path, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                        
                    # Query to match this page image to its database page record
                    cursor.execute("""
                        SELECT dp.document_id, dp.batch_id, dp.page_number, pb.original_pdf_name
                        FROM document_pages dp
                        JOIN processed_batches pb ON dp.batch_id = pb.batch_id
                        WHERE dp.image_path LIKE ?
                    """, (f"%/{image_basename}.png",))
                    row = cursor.fetchone()
                    
                    if row:
                        doc_id = row["document_id"]
                        batch_id = row["batch_id"]
                        page_number = row["page_number"]
                        pdf_name = row["original_pdf_name"]
                        
                        # Recreate document if missing
                        if not doc_id:
                            import uuid
                            doc_id = f"doc_{uuid.uuid4().hex[:12]}"
                            
                            # Determine validation status
                            validation_meta = payload.get("validation_meta", {})
                            is_complete = validation_meta.get("is_complete", True)
                            missing = validation_meta.get("missing_pages", [])
                            status_code = "PROCESSED"
                            error_reason = None
                            if not is_complete:
                                status_code = "FAILED"
                                error_reason = f"เอกสารสแกนมาไม่ครบถ้วน: ขาดหน้า {', '.join(map(str, missing))}"
                                
                            doc_number = payload.get("doc_number", "")
                            doc_date = payload.get("transaction_date", "")
                            entity_name = payload.get("merchant_name", "")
                            fin_summary = payload.get("financial_summary", {})
                            total_amount = fin_summary.get("net_amount", 0.0)
                            tax_id = payload.get("tax_id", "")
                            payment_method = payload.get("payment_method", "")
                            search_text = f"{doc_number} {entity_name} {tax_id} {payment_method}".strip()
                            
                            # Create document in SQLite
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
                                conn=conn
                            )
                            
                            # Link page to the newly created document
                            cursor.execute("""
                                UPDATE document_pages
                                SET document_id = ?, status_code = ?, error_reason = ?
                                WHERE batch_id = ? AND page_number = ?
                            """, (doc_id, status_code, error_reason, batch_id, page_number))
                            
                            logger.info(f"Re-registered missing document record '{doc_id}' for '{file}'")
                        
                        # Insert to relational tables
                        success = insert_relational_receipt(doc_id, payload, pdf_name, conn=conn)
                        if success:
                            logger.info(f"Migrated relational data for doc '{doc_id}' from '{file}'")
                            migrated_count += 1
                        else:
                            logger.error(f"Failed to migrate relational data for doc '{doc_id}' from '{file}'")
                    else:
                        logger.warning(f"No database document page found matching image basename: '{image_basename}'")
                        skipped_count += 1
                        
        conn.commit()
        logger.info(f"Data migration finished. Successfully migrated: {migrated_count} receipt(s), skipped: {skipped_count}.")
    except Exception as e:
        logger.error(f"Failed during historical data migration: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()

if __name__ == "__main__":
    seed_from_queue()
