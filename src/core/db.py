import os
import json
import sqlite3
import hashlib
from datetime import datetime
from loguru import logger

def get_db_connection(settings_path: str = "configs/settings.json") -> sqlite3.Connection:
    """
    Establishes a connection to the centralized SQLite database.
    Resolves path dynamically from settings.json 'storage_root'.
    """
    storage_root = "pipeline_storage"
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            storage_root = settings.get("storage_root", "pipeline_storage")
        except Exception as e:
            logger.warning(f"Failed to read settings.json for DB connection: {e}")
            
    os.makedirs(storage_root, exist_ok=True)
    db_path = os.environ.get("DB_PATH_OVERRIDE")
    if not db_path:
        db_path = os.path.join(storage_root, "pipeline.db").replace("\\", "/")
    
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    # Enable dict factory to easily return results as dictionaries
    conn.row_factory = sqlite3.Row
    return conn

def initialize_db_schema():
    """
    Creates relational database schema if tables do not exist.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. document_domains
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_domains (
                domain_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0
            )
        """)
        
        # 2. document_sources
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_sources (
                source_id TEXT PRIMARY KEY,
                domain_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (domain_id) REFERENCES document_domains(domain_id) ON DELETE CASCADE
            )
        """)
        
        # 3. document_statuses
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_statuses (
                status_code TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                description TEXT
            )
        """)
        
        # 4. processed_batches
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_batches (
                batch_id TEXT PRIMARY KEY,
                original_pdf_name TEXT NOT NULL,
                total_pages INTEGER NOT NULL,
                storage_path TEXT NOT NULL,
                file_hash TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        # 5. documents
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                domain_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                status_code TEXT NOT NULL,
                doc_number TEXT,
                doc_date TEXT,
                entity_name TEXT,
                total_amount REAL,
                search_text TEXT,
                data_payload TEXT,
                error_reason TEXT,
                is_locked INTEGER DEFAULT 0,
                is_manually_edited INTEGER DEFAULT 0,
                confirmed_by TEXT,
                confirmed_at TEXT,
                model_used TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (batch_id) REFERENCES processed_batches(batch_id) ON DELETE CASCADE,
                FOREIGN KEY (domain_id) REFERENCES document_domains(domain_id),
                FOREIGN KEY (source_id) REFERENCES document_sources(source_id),
                FOREIGN KEY (status_code) REFERENCES document_statuses(status_code)
            )
        """)
        
        # 6. document_pages
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_pages (
                page_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                document_id TEXT,
                page_number INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                status_code TEXT NOT NULL,
                error_reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (batch_id) REFERENCES processed_batches(batch_id) ON DELETE CASCADE,
                FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE SET NULL
            )
        """)

        # 7. api_credentials
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_credentials (
                credential_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model_name TEXT NOT NULL,
                api_key_env TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                last_active_at TEXT,
                error_count INTEGER DEFAULT 0
            )
        """)

        # 8. api_call_logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_call_logs (
                log_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                credential_id TEXT,
                provider TEXT NOT NULL,
                model_name TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                request_pages TEXT,
                status TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                latency_ms REAL,
                error_reason TEXT,
                raw_response TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (batch_id) REFERENCES processed_batches(batch_id) ON DELETE CASCADE,
                FOREIGN KEY (credential_id) REFERENCES api_credentials(credential_id) ON DELETE SET NULL
            )
        """)

        # 9. application_logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS application_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                module TEXT,
                function TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        logger.info("Relational SQLite schema initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database schema: {e}")
        raise e
    finally:
        if conn:
            conn.close()

def seed_initial_data(configs_dir: str = "configs"):
    """
    Seeds statuses, domains (from configs/document_domains.json), and discoverable sources.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Seed document statuses
        statuses = [
            ("PENDING", "Pending Review", "Document is waiting for initial preprocessing or splitting."),
            ("PREPROCESSED", "Preprocessed", "Document is split and matched, ready for AI extraction."),
            ("PROCESSED", "Processed", "AI successfully extracted document payload, waiting for human audit."),
            ("APPROVED", "Approved", "Document has been approved by the user and locked."),
            ("REJECTED", "Rejected", "Document has been rejected by the user."),
            ("COMPLETED", "Completed", "Document payload has been exported to CSV and archived."),
            ("FAILED", "Failed", "Document processing failed due to technical error or missing scans.")
        ]
        cursor.executemany("""
            INSERT OR REPLACE INTO document_statuses (status_code, display_name, description)
            VALUES (?, ?, ?)
        """, statuses)
        
        # 2. Seed document domains from config file
        domains_json = os.path.join(configs_dir, "document_domains.json")
        if os.path.exists(domains_json):
            with open(domains_json, "r", encoding="utf-8") as f:
                domains_data = json.load(f)
            for d in domains_data:
                cursor.execute("""
                    INSERT OR IGNORE INTO document_domains (domain_id, display_name, is_active, sort_order)
                    VALUES (?, ?, ?, ?)
                """, (d["domain_id"], d["display_name"], 1 if d.get("is_active", True) else 0, d.get("sort_order", 0)))
                
        # 3. Discover and seed document sources from domain directory scans
        domains_dir = os.path.join(configs_dir, "domains")
        if os.path.exists(domains_dir):
            for domain_id in os.listdir(domains_dir):
                domain_path = os.path.join(domains_dir, domain_id)
                if os.path.isdir(domain_path):
                    sources_dir = os.path.join(domain_path, "sources")
                    if os.path.exists(sources_dir):
                        # Always insert _default source
                        cursor.execute("""
                            INSERT OR IGNORE INTO document_sources (source_id, domain_id, display_name, is_active)
                            VALUES (?, ?, ?, ?)
                        """, ("_default", domain_id, "Default Fallback", 1))
                        
                        for entry in os.listdir(sources_dir):
                            entry_path = os.path.join(sources_dir, entry)
                            if os.path.isdir(entry_path) and not entry.startswith("_"):
                                # Format display name (e.g. grab_thailand -> Grab Thailand)
                                display_name = entry.replace("_", " ").title()
                                cursor.execute("""
                                    INSERT OR IGNORE INTO document_sources (source_id, domain_id, display_name, is_active)
                                    VALUES (?, ?, ?, ?)
                                """, (entry, domain_id, display_name, 1))
                                
        # 4. Seed default API credentials
        cursor.execute("""
            INSERT OR IGNORE INTO api_credentials (credential_id, provider, model_name, api_key_env, is_active, last_active_at, error_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("cred_gemini_default", "gemini", "gemini-3.5-flash", "GEMINI_API_KEY", 1, None, 0))
                                
        conn.commit()
        logger.info("Database seeding completed.")
    except Exception as e:
        logger.error(f"Failed to seed SQLite database: {e}")
    finally:
        if conn:
            conn.close()

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
                "filename": row["original_pdf_name"],
                "created_at": row["created_at"],
                "status": row["status_code"] or "PENDING",
                "domain": row["domain_id"] or "",
                "source": row["source_id"] or ""
            }
            return True, metadata
    except Exception as e:
        logger.error(f"Failed to check duplicate batch hash: {e}")
    finally:
        if conn:
            conn.close()
    return False, None

def create_batch(batch_id: str, original_pdf_name: str, total_pages: int, storage_path: str, file_hash: str) -> bool:
    """
    Inserts a new batch record into processed_batches.
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

def create_document(document_id: str, batch_id: str, domain_id: str, source_id: str, status_code: str, 
                    doc_number: str = None, doc_date: str = None, entity_name: str = None, 
                    total_amount: float = None, search_text: str = None, data_payload: str = None, 
                    error_reason: str = None, model_used: str = None, input_tokens: int = None,
                    output_tokens: int = None, conn: sqlite3.Connection = None) -> bool:
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
                model_used, input_tokens, output_tokens, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (document_id, batch_id, domain_id, source_id, status_code, doc_number, doc_date,
              entity_name, total_amount, search_text, data_payload, error_reason,
              model_used, input_tokens, output_tokens, created_at))
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
            ORDER BY doc.created_at DESC
        """, (domain_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch pending documents: {e}")
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

def update_document_to_failed(document_id: str, error_reason: str) -> bool:
    """
    Sets status as FAILED and logs error reason.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        updated_at = datetime.now().isoformat()
        cursor.execute("""
            UPDATE documents
            SET status_code = 'FAILED',
                error_reason = ?,
                updated_at = ?
            WHERE document_id = ?
        """, (error_reason, updated_at, document_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to mark document as failed: {e}")
        return False
    finally:
        if conn:
            conn.close()

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

def search_documents(domain_id: str, source_id: str = None, start_date: str = None, 
                     end_date: str = None, keyword: str = None) -> list[dict]:
    """
    Performs dynamic lookup of documents based on domains, sources, dates, and keywords.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT doc.*, pb.original_pdf_name, pb.storage_path
            FROM documents doc
            JOIN processed_batches pb ON doc.batch_id = pb.batch_id
            WHERE doc.domain_id = ?
        """
        params = [domain_id]
        
        if source_id and source_id != "All":
            query += " AND doc.source_id = ?"
            params.append(source_id)
            
        if start_date:
            query += " AND doc.doc_date >= ?"
            params.append(start_date)
            
        if end_date:
            query += " AND doc.doc_date <= ?"
            params.append(end_date)
            
        if keyword:
            query += " AND (doc.doc_number LIKE ? OR doc.entity_name LIKE ? OR doc.search_text LIKE ?)"
            like_kw = f"%{keyword}%"
            params.extend([like_kw, like_kw, like_kw])
            
        query += " ORDER BY doc.created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to search documents: {e}")
    finally:
        if conn:
            conn.close()
    return []

def get_domains() -> list[dict]:
    """
    Returns list of domains from database.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM document_domains ORDER BY sort_order ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to load domains: {e}")
    finally:
        if conn:
            conn.close()
    return []

def get_sources(domain_id: str) -> list[dict]:
    """
    Returns list of sources for a domain from database.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM document_sources WHERE domain_id = ?", (domain_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to load sources for domain '{domain_id}': {e}")
    finally:
        if conn:
            conn.close()
    return []

def update_domain_active_status(domain_id: str, is_active: int) -> bool:
    """
    Toggles is_active for a domain.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE document_domains SET is_active = ? WHERE domain_id = ?", (is_active, domain_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to toggle domain active status: {e}")
        return False
    finally:
        if conn:
            conn.close()

def update_source_active_status(source_id: str, is_active: int) -> bool:
    """
    Toggles is_active for a source.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE document_sources SET is_active = ? WHERE source_id = ?", (is_active, source_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to toggle source active status: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_active_credentials(provider: str, model_name: str) -> list[dict]:
    """
    Retrieves all active API credentials for a specific provider and model.
    Sorted by last_active_at DESC (last working key first).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM api_credentials
            WHERE provider = ? AND model_name = ? AND is_active = 1
            ORDER BY last_active_at DESC, credential_id ASC
        """, (provider, model_name))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to get active credentials: {e}")
        return []
    finally:
        if conn:
            conn.close()

def update_credential_status(credential_id: str, last_active_at: str = None, error_count: int = None, is_active: int = None) -> bool:
    """
    Updates status, error_count, and last_active_at timestamp for a credential.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if last_active_at is not None:
            updates.append("last_active_at = ?")
            params.append(last_active_at)
        if error_count is not None:
            updates.append("error_count = ?")
            params.append(error_count)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(is_active)
            
        if not updates:
            return True
            
        params.append(credential_id)
        query = f"UPDATE api_credentials SET {', '.join(updates)} WHERE credential_id = ?"
        
        cursor.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update credential status: {e}")
        return False
    finally:
        if conn:
            conn.close()

def create_api_call_log(log_id: str, batch_id: str, credential_id: str, provider: str, model_name: str,
                        chunk_index: int, request_pages: str, status: str, input_tokens: int = 0,
                        output_tokens: int = 0, latency_ms: float = None, error_reason: str = None,
                        raw_response: str = None) -> bool:
    """
    Inserts a new API call log record.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        created_at = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO api_call_logs (
                log_id, batch_id, credential_id, provider, model_name, chunk_index,
                request_pages, status, input_tokens, output_tokens, latency_ms,
                error_reason, raw_response, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, batch_id, credential_id, provider, model_name, chunk_index,
              request_pages, status, input_tokens, output_tokens, latency_ms,
              error_reason, raw_response, created_at))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to create API call log: {e}")
        return False
    finally:
        if conn:
            conn.close()
