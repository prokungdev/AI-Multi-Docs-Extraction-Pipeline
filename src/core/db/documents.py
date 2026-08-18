import os
import json
import sqlite3
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Tuple
from loguru import logger
from .connection import get_db_connection

def calculate_file_hash(file_path: str) -> str:
    """
    Computes the SHA-256 hash of a file's binary content.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def check_duplicate_document(file_hash: str) -> tuple[bool, dict | None]:
    """
    Checks if a batch with the given SHA-256 hash already exists.
    Returns: (is_duplicate, batch_metadata_dict)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pb.batch_id, pb.original_pdf_name, pb.created_at, doc.status_code, doc.domain_id, doc.source_id
            FROM processed_batches pb
            LEFT JOIN documents doc ON pb.batch_id = doc.batch_id
            WHERE pb.file_hash = ?
        """, (file_hash,))
        row = cursor.fetchone()
        if row:
            metadata = {
                "batch_id": row["batch_id"],
                "original_pdf_name": row["original_pdf_name"],
                "created_at": row["created_at"],
                "status": row["status_code"] if row["status_code"] else "PENDING",
                "domain": row["domain_id"] if row["domain_id"] else "expense_receipt",
                "source": row["source_id"] if row["source_id"] else "_default"
            }
            return True, metadata
    except Exception as e:
        logger.error(f"Error checking duplicate document hash: {e}")
    finally:
        if conn:
            conn.close()
    return False, None

def create_batch(batch_id: str, original_pdf_name: str, total_pages: int, storage_path: str, file_hash: str) -> bool:
    """
    Inserts a new batch record.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        created_at = datetime.now().isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO processed_batches (batch_id, original_pdf_name, total_pages, storage_path, file_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (batch_id, original_pdf_name, total_pages, storage_path, file_hash, created_at))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to create batch: {e}")
        return False
    finally:
        if conn:
            conn.close()

def create_page(page_id: str, batch_id: str, page_number: int, image_path: str, status_code: str, error_reason: str = None) -> bool:
    """
    Inserts a new page record.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        created_at = datetime.now().isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO document_pages (page_id, batch_id, page_number, image_path, status_code, error_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (page_id, batch_id, page_number, image_path, status_code, error_reason, created_at))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to create page: {e}")
        return False
    finally:
        if conn:
            conn.close()

def update_page(page_id: str, image_path: str = None, status_code: str = None, error_reason: str = None) -> bool:
    """
    Updates an existing page record (e.g. image_path, status_code, error_reason).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        fields = []
        params = []
        if image_path is not None:
            fields.append("image_path = ?")
            params.append(image_path)
        if status_code is not None:
            fields.append("status_code = ?")
            params.append(status_code)
        if error_reason is not None:
            fields.append("error_reason = ?")
            params.append(error_reason)
        if not fields:
            return True
        params.append(page_id)
        query = f"UPDATE document_pages SET {', '.join(fields)} WHERE page_id = ?"
        cursor.execute(query, tuple(params))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update page {page_id}: {e}")
        return False
    finally:
        if conn:
            conn.close()

def update_page_status(page_id: str, status_code: str, error_reason: str = None, conn: sqlite3.Connection = None) -> bool:
    """
    Convenience helper to update status and error reason of a page.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE document_pages
            SET status_code = ?, error_reason = ?
            WHERE page_id = ?
        """, (status_code, error_reason, page_id))
        if should_close:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update page status for {page_id}: {e}")
        return False
    finally:
        if should_close and conn:
            conn.close()

def update_pages_status_batch(updates: List[Tuple[str, str | None, str, int]], conn: sqlite3.Connection = None) -> bool:
    """
    Batch update page statuses using executemany for high performance.
    Args:
        updates: List of tuples (status_code, error_reason, batch_id, page_number)
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.executemany("""
            UPDATE document_pages
            SET status_code = ?, error_reason = ?
            WHERE batch_id = ? AND page_number = ?
        """, updates)
        if should_close:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to batch update page statuses: {e}")
        return False
    finally:
        if should_close and conn:
            conn.close()

def create_document(document_id: str, batch_id: str, domain_id: str, source_id: str, status_code: str, 
                    doc_number: str = None, doc_date: str = None, entity_name: str = None, 
                    total_amount: float = None, search_text: str = None, data_payload: str = None, 
                    error_reason: str = None, model_used: str = None, input_tokens: int = None,
                    output_tokens: int = None, conn: sqlite3.Connection = None,
                    overall_confidence: float = None, confidence_level: str = None,
                    is_blurry: int = None, has_ambiguous_fields: int = None,
                    confidence_notes: str = None, review_priority: str = None,
                    auto_approved: int = None) -> bool:
    """
    Inserts a new document record.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        created_at = datetime.now().isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO documents (
                document_id, batch_id, domain_id, source_id, status_code, doc_number, doc_date, 
                entity_name, total_amount, search_text, data_payload, error_reason,
                model_used, input_tokens, output_tokens, overall_confidence, confidence_level,
                is_blurry, has_ambiguous_fields, confidence_notes, review_priority, auto_approved,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (document_id, batch_id, domain_id, source_id, status_code, doc_number, doc_date,
              entity_name, total_amount, search_text, data_payload, error_reason,
              model_used, input_tokens, output_tokens, overall_confidence, confidence_level,
              is_blurry, has_ambiguous_fields, confidence_notes, review_priority, auto_approved,
              created_at))
        if should_close:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to create document: {e}")
        return False
    finally:
        if should_close and conn:
            conn.close()

def link_pages_to_document(batch_id: str, document_id: str, status_code: str = None, conn: sqlite3.Connection = None):
    """
    Links all pages in a batch to a specific document and optionally updates their status.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        if status_code:
            cursor.execute("""
                UPDATE document_pages
                SET document_id = ?, status_code = ?
                WHERE batch_id = ?
            """, (document_id, status_code, batch_id))
        else:
            cursor.execute("""
                UPDATE document_pages
                SET document_id = ?
                WHERE batch_id = ?
            """, (document_id, batch_id))
        if should_close:
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to link pages to document: {e}")
    finally:
        if should_close and conn:
            conn.close()

def get_document_by_id(document_id: str) -> dict | None:
    """
    Fetches a single document by its ID.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
    except Exception as e:
        logger.error(f"Failed to fetch document by ID: {e}")
    finally:
        if conn:
            conn.close()
    return None

def get_document_pages(document_id: str) -> list[dict]:
    """
    Retrieves all pages associated with a document.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM document_pages WHERE document_id = ? ORDER BY page_number ASC", (document_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch pages for document: {e}")
    finally:
        if conn:
            conn.close()
    return []

def get_batch_pages(batch_id: str) -> list[dict]:
    """
    Retrieves all pages associated with a batch.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM document_pages WHERE batch_id = ? ORDER BY page_number ASC", (batch_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch pages for batch: {e}")
    finally:
        if conn:
            conn.close()
    return []

def get_pending_documents(domain_id: str) -> list[dict]:
    """
    Retrieves all documents in a domain that are not approved (unlocked).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT doc.*, pb.original_pdf_name, pb.storage_path
            FROM documents doc
            JOIN processed_batches pb ON doc.batch_id = pb.batch_id
            WHERE doc.domain_id = ? AND doc.is_locked = 0
            ORDER BY 
                CASE doc.review_priority
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                    ELSE 4
                END ASC,
                doc.created_at DESC
        """, (domain_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch pending documents: {e}")
    finally:
        if conn:
            conn.close()
    return []

def get_all_documents(domain_id: str) -> list[dict]:
    """
    Retrieves all documents in a domain with batch metadata.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT doc.*, pb.original_pdf_name, pb.storage_path
            FROM documents doc
            JOIN processed_batches pb ON doc.batch_id = pb.batch_id
            WHERE doc.domain_id = ?
            ORDER BY doc.created_at DESC
        """, (domain_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch all documents: {e}")
    finally:
        if conn:
            conn.close()
    return []

def update_document_to_approved(document_id: str, doc_number: str, doc_date: str, entity_name: str, 
                                total_amount: float, data_payload: str, confirmed_by: str) -> bool:
    """
    Locks the document and marks its status as APPROVED.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        confirmed_at = datetime.now().isoformat()
        cursor.execute("""
            UPDATE documents
            SET status_code = 'APPROVED',
                doc_number = ?,
                doc_date = ?,
                entity_name = ?,
                total_amount = ?,
                data_payload = ?,
                is_locked = 1,
                confirmed_by = ?,
                confirmed_at = ?,
                updated_at = ?
            WHERE document_id = ?
        """, (doc_number, doc_date, entity_name, total_amount, data_payload, confirmed_by, confirmed_at, confirmed_at, document_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to approve document: {e}")
        return False
    finally:
        if conn:
            conn.close()

def update_document_to_rejected(document_id: str, confirmed_by: str = "admin", reason: str = None) -> bool:
    """
    Marks a document as REJECTED and locks it.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        confirmed_at = datetime.now().isoformat()
        cursor.execute("""
            UPDATE documents
            SET status_code = 'REJECTED',
                is_locked = 1,
                confirmed_by = ?,
                confirmed_at = ?,
                error_reason = ?,
                updated_at = ?
            WHERE document_id = ?
        """, (confirmed_by, confirmed_at, reason, confirmed_at, document_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to reject document: {e}")
        return False
    finally:
        if conn:
            conn.close()

def update_document_status(document_id: str, status_code: str, error_reason: str = None, conn: sqlite3.Connection = None) -> bool:
    """
    Updates the status code and optional error reason of a document.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        updated_at = datetime.now().isoformat()
        cursor.execute("""
            UPDATE documents
            SET status_code = ?,
                error_reason = ?,
                updated_at = ?
            WHERE document_id = ?
        """, (status_code, error_reason, updated_at, document_id))
        if should_close:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update document status: {e}")
        return False
    finally:
        if should_close and conn:
            conn.close()

def update_document_to_failed(document_id: str, error_reason: str) -> bool:
    """
    Sets status as FAILED and logs error reason.
    """
    return update_document_status(document_id, "FAILED", error_reason)

def update_document_payload(document_id: str, data_payload: str, status_code: str = "PROCESSED", 
                            doc_number: str = None, doc_date: str = None, entity_name: str = None, 
                            total_amount: float = None, is_manually_edited: int = 0) -> bool:
    """
    Updates the extracted payload fields.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        updated_at = datetime.now().isoformat()
        cursor.execute("""
            UPDATE documents
            SET status_code = ?,
                data_payload = ?,
                doc_number = ?,
                doc_date = ?,
                entity_name = ?,
                total_amount = ?,
                is_manually_edited = ?,
                error_reason = NULL,
                updated_at = ?
            WHERE document_id = ?
        """, (status_code, data_payload, doc_number, doc_date, entity_name, total_amount, is_manually_edited, updated_at, document_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update document payload: {e}")
        return False
    finally:
        if conn:
            conn.close()

def update_document_metadata(document_id: str, overall_confidence: float, confidence_level: str,
                             is_blurry: int, has_ambiguous_fields: int, confidence_notes: str,
                             review_priority: str, auto_approved: int, conn: sqlite3.Connection = None) -> bool:
    """
    Updates the evaluation metadata columns for a document.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        updated_at = datetime.now().isoformat()
        cursor.execute("""
            UPDATE documents
            SET overall_confidence = ?,
                confidence_level = ?,
                is_blurry = ?,
                has_ambiguous_fields = ?,
                confidence_notes = ?,
                review_priority = ?,
                auto_approved = ?,
                updated_at = ?
            WHERE document_id = ?
        """, (overall_confidence, confidence_level, is_blurry, has_ambiguous_fields, confidence_notes, review_priority, auto_approved, updated_at, document_id))
        if should_close:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update document metadata: {e}")
        return False
    finally:
        if should_close and conn:
            conn.close()

def search_documents(domain_id: str, source_id: str = None, start_date: str = None, 
                     end_date: str = None, keyword: str = None) -> list[dict]:
    """
    Performs dynamic lookup of documents based on domains, sources, dates, and keywords.
    Uses clean list comprehensions for dynamic conditions.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        conditions = ["doc.domain_id = ?"]
        params = [domain_id]
        
        if source_id and source_id != "All":
            conditions.append("doc.source_id = ?")
            params.append(source_id)
            
        if start_date:
            conditions.append("doc.doc_date >= ?")
            params.append(start_date)
            
        if end_date:
            conditions.append("doc.doc_date <= ?")
            params.append(end_date)
            
        if keyword:
            conditions.append("(doc.doc_number LIKE ? OR doc.entity_name LIKE ? OR doc.search_text LIKE ?)")
            like_kw = f"%{keyword}%"
            params.extend([like_kw, like_kw, like_kw])
            
        query = f"""
            SELECT doc.*, pb.original_pdf_name, pb.storage_path
            FROM documents doc
            JOIN processed_batches pb ON doc.batch_id = pb.batch_id
            WHERE {' AND '.join(conditions)}
            ORDER BY doc.created_at DESC
        """
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to search documents: {e}")
    finally:
        if conn:
            conn.close()
    return []
