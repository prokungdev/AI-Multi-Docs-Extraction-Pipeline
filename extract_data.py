import os
import json
import uuid
import copy
from dotenv import load_dotenv
from src.core.db import (
    get_db_connection,
    create_document,
    link_pages_to_document,
    update_document_to_failed
)
from src.core.extractor import extract_document_data
from src.core.config_loader import load_system_settings
from src.core.logger import setup_logger
from main import merge_chunk_payloads

def main():
    setup_logger()
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
        
        # 1. Fetch batches that do not have a document record yet
        cursor.execute("""
            SELECT pb.batch_id, pb.original_pdf_name, pb.storage_path
            FROM processed_batches pb
            LEFT JOIN documents doc ON pb.batch_id = doc.batch_id
            WHERE doc.document_id IS NULL
        """)
        batches = cursor.fetchall()
        conn.close()
        conn = None
        
        if not batches:
            print("[*] No pending batches requiring data extraction.")
            return
            
        print(f"[*] Found {len(batches)} batch(es) to process and extract data...")
        
        max_images = settings.get("max_images_per_request", 50)
        
        for b in batches:
            batch_id = b["batch_id"]
            pdf_name = b["original_pdf_name"]
            storage_path = b["storage_path"]
            
            # Resolve matched source from storage path
            folder_name = os.path.basename(storage_path)
            source = "_default" if folder_name == "_uncategorized" else folder_name
            
            print(f"\n--- Extracting Batch: {pdf_name} (ID: {batch_id}) ---")
            print(f"    Source Merchant: {source}")
            
            # Fetch all split page image paths using a temporary connection to avoid locks during API call
            temp_conn = get_db_connection()
            temp_cursor = temp_conn.cursor()
            temp_cursor.execute("""
                SELECT image_path, page_number FROM document_pages
                WHERE batch_id = ?
                ORDER BY page_number ASC
            """, (batch_id,))
            pages = temp_cursor.fetchall()
            temp_conn.close()
            
            image_paths = [p["image_path"] for p in pages]
            
            if not image_paths:
                print("    [-] Error: No split page images found for this batch. Skipping.")
                continue
                
            payloads = []
            extraction_success = True
            err_msg = ""
            
            # 2. Call Gemini extraction engine (Auto-Chunking)
            if len(image_paths) <= max_images:
                print(f"    [+] Processing all {len(image_paths)} pages in a single Request...")
                try:
                    page_data = extract_document_data(image_paths, source, domain, batch_id=batch_id, chunk_index=1)
                    payloads.append(page_data)
                except Exception as e:
                    print(f"    [-] Structured extraction failed: {e}")
                    extraction_success = False
                    err_msg = f"Gemini Extraction Exception: {str(e)}"
            else:
                # Page count > max limit, slice into chunks
                chunks = [image_paths[i:i + max_images] for i in range(0, len(image_paths), max_images)]
                print(f"    [!] Page count ({len(image_paths)}) exceeds limit ({max_images}). Split into {len(chunks)} Requests...")
                
                for idx, chunk in enumerate(chunks):
                    print(f"    [+] Sending Part {idx + 1} of {len(chunks)} (pages {idx*max_images + 1} to {idx*max_images + len(chunk)})...")
                    try:
                        part_data = extract_document_data(chunk, source, domain, batch_id=batch_id, chunk_index=idx + 1)
                        payloads.append(part_data)
                    except Exception as e:
                        print(f"    [-] Part {idx + 1} extraction failed: {e}")
                        extraction_success = False
                        err_msg = f"Part {idx + 1} Gemini Extraction Exception: {str(e)}"
                        break
            
            # 3. Open connection for batch data persistence to group all updates in a single transaction
            batch_conn = get_db_connection()
            batch_cursor = batch_conn.cursor()
            
            try:
                if not extraction_success:
                    # Register a FAILED document record in DB so it shows in UI with error traceback
                    fallback_doc_id = f"doc_{uuid.uuid4().hex[:12]}"
                    create_document(
                        document_id=fallback_doc_id,
                        batch_id=batch_id,
                        domain_id=domain,
                        source_id=source,
                        status_code="FAILED",
                        error_reason=err_msg,
                        conn=batch_conn
                    )
                    link_pages_to_document(batch_id, fallback_doc_id, status_code="FAILED", conn=batch_conn)
                    batch_conn.commit()
                    print(f"    [!] Registered failed batch document record '{fallback_doc_id}' in SQLite.")
                    continue
                    
                # Process extracted documents list
                all_docs = []
                model_used = None
                total_input_tokens = 0
                total_output_tokens = 0
                
                for p_load in payloads:
                    # Get the metadata for token tracking
                    meta = p_load.get("_metadata", {})
                    if meta:
                        model_used = meta.get("model_used")
                        total_input_tokens += meta.get("input_tokens", 0)
                        total_output_tokens += meta.get("output_tokens", 0)
                    
                    # Add extracted documents to the main list
                    docs_in_payload = p_load.get("extracted_documents", [])
                    all_docs.extend(docs_in_payload)
                
                if not all_docs:
                    print("    [-] Warning: AI returned empty extracted documents list. Marking batch pages as FAILED.")
                    fallback_doc_id = f"doc_{uuid.uuid4().hex[:12]}"
                    create_document(
                        document_id=fallback_doc_id,
                        batch_id=batch_id,
                        domain_id=domain,
                        source_id=source,
                        status_code="FAILED",
                        error_reason="AI returned no extracted documents.",
                        conn=batch_conn
                    )
                    link_pages_to_document(batch_id, fallback_doc_id, status_code="FAILED", conn=batch_conn)
                    batch_conn.commit()
                    continue
                    
                # Attribute tokens per page/document
                doc_count = len(all_docs)
                input_tokens_per_doc = int(total_input_tokens / doc_count)
                output_tokens_per_doc = int(total_output_tokens / doc_count)
                
                # Map page numbers to documents
                # Group pages in SQLite for quick lookups
                batch_cursor.execute("SELECT page_id, page_number, image_path FROM document_pages WHERE batch_id = ?", (batch_id,))
                db_pages = {p["page_number"]: {"page_id": p["page_id"], "image_path": p["image_path"]} for p in batch_cursor.fetchall()}
                
                # Ensure source directory exists in 03_processing_queue
                source_queue_dir = os.path.join(queue_dir, source)
                os.makedirs(source_queue_dir, exist_ok=True)
                
                for doc_payload in all_docs:
                    logical_page = doc_payload.get("logical_page_number", 1)
                    
                    # Find matching page
                    page_info = db_pages.get(logical_page)
                    if not page_info:
                        print(f"    [!] Warning: Logical page number {logical_page} not found in database. Skipping.")
                        continue
                        
                    image_path = page_info["image_path"]
                    image_basename = os.path.splitext(os.path.basename(image_path))[0]
                    
                    # Generate unique doc_id for this page document
                    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
                    
                    # Evaluate validation metadata for this page
                    val_meta = doc_payload.get("validation_meta", {})
                    is_complete = val_meta.get("is_complete", True)
                    missing = val_meta.get("missing_pages", [])
                    
                    status_code = "PROCESSED"
                    error_reason = None
                    if not is_complete:
                        status_code = "FAILED"
                        error_reason = f"เอกสารสแกนมาไม่ครบถ้วน: ขาดหน้า {', '.join(map(str, missing))}"
                        print(f"    [!] Scan Error for Page {logical_page}: {error_reason}")
                    
                    # Inject token usage metadata into the page-specific JSON file
                    doc_payload["_metadata"] = {
                        "model_used": model_used,
                        "input_tokens": input_tokens_per_doc,
                        "output_tokens": output_tokens_per_doc
                    }
                    
                    # Save JSON file inside source directory
                    json_filename = f"{image_basename}.json"
                    page_json_path = os.path.join(source_queue_dir, json_filename)
                    with open(page_json_path, "w", encoding="utf-8") as f:
                        json.dump(doc_payload, f, ensure_ascii=False, indent=2)
                    
                    # Extract DB representation fields
                    doc_number = doc_payload.get("doc_number", "")
                    doc_date = doc_payload.get("transaction_date", "")
                    entity_name = doc_payload.get("merchant_name", "")
                    
                    fin_summary = doc_payload.get("financial_summary", {})
                    total_amount = fin_summary.get("net_amount", 0.0)
                    
                    tax_id = doc_payload.get("tax_id", "")
                    payment_method = doc_payload.get("payment_method", "")
                    search_text = f"{doc_number} {entity_name} {tax_id} {payment_method}".strip()
                    
                    # Insert document into SQLite
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
                        data_payload=json.dumps(doc_payload, ensure_ascii=False),
                        error_reason=error_reason,
                        model_used=model_used,
                        input_tokens=input_tokens_per_doc,
                        output_tokens=output_tokens_per_doc,
                        conn=batch_conn
                    )
                    
                    # Link page to document and update status
                    batch_cursor.execute("""
                        UPDATE document_pages
                        SET document_id = ?, status_code = ?, error_reason = ?
                        WHERE batch_id = ? AND page_number = ?
                    """, (doc_id, status_code, error_reason, batch_id, logical_page))
                    
                    print(f"    [+] Registered Page {logical_page} -> {source}/{json_filename} (Status: {status_code})")
                
                batch_conn.commit()
            except Exception as loop_e:
                batch_conn.rollback()
                print(f"    [-] Error during batch transaction write: {loop_e}")
                raise loop_e
            finally:
                batch_conn.close()
            
        print("\n[SUCCESS] Completed Step 4! Data extraction and JSON registration completed.")
    except Exception as e:
        print(f"[-] Error during data extraction execution: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
