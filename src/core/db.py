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

def get_log_db_connection(settings_path: str = "configs/settings.json") -> sqlite3.Connection:
    """
    Establishes a connection to the separate logs SQLite database (logs/logs.db).
    """
    logs_dir = "logs"
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            logging_cfg = settings.get("logging", {})
            logs_dir = logging_cfg.get("logs_dir", "logs")
        except Exception:
            pass
            
    os.makedirs(logs_dir, exist_ok=True)
    db_path = os.path.join(logs_dir, "logs.db").replace("\\", "/")
    
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def initialize_log_db_schema(settings_path: str = "configs/settings.json"):
    """
    Initializes the logging database schema (application_logs table).
    """
    conn = None
    try:
        conn = get_log_db_connection(settings_path)
        cursor = conn.cursor()
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
    except Exception as e:
        print(f"Warning: Failed to initialize SQLite log database schema: {e}")
    finally:
        if conn:
            conn.close()

def initialize_db_schema():
    """
    Creates relational database schema if tables do not exist.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. document_sources (No FK constraint to document_domains)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_sources (
                source_id TEXT PRIMARY KEY,
                domain_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # 2. document_statuses
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_statuses (
                status_code TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                description TEXT
            )
        """)
        
        # 3. processed_batches
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
        
        # 4. documents (No FK constraint to document_domains)
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
                FOREIGN KEY (source_id) REFERENCES document_sources(source_id),
                FOREIGN KEY (status_code) REFERENCES document_statuses(status_code)
            )
        """)
        
        # 5. document_pages
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

        # 6. merchant_master
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS merchant_master (
                merchant_id TEXT PRIMARY KEY,
                tax_id TEXT UNIQUE,
                merchant_name TEXT NOT NULL,
                default_wht_rate REAL DEFAULT 0.0,
                is_vat_registered INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)

        # 7. expense_receipt
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expense_receipt (
                receipt_id TEXT PRIMARY KEY,
                document_id TEXT UNIQUE,
                merchant_id TEXT,
                transaction_date TEXT,
                merchant_name TEXT,
                tax_id TEXT,
                expense_category TEXT,
                subtotal REAL,
                discount REAL,
                vat_amount REAL,
                net_amount REAL,
                payment_method TEXT,
                source_file_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
                FOREIGN KEY (merchant_id) REFERENCES merchant_master(merchant_id) ON DELETE SET NULL
            )
        """)

        # 8. expense_receipt_d
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expense_receipt_d (
                item_id TEXT PRIMARY KEY,
                receipt_id TEXT NOT NULL,
                item_name TEXT NOT NULL,
                qty INTEGER DEFAULT 1,
                unit_price REAL,
                total_price REAL,
                FOREIGN KEY (receipt_id) REFERENCES expense_receipt(receipt_id) ON DELETE CASCADE
            )
        """)

        # 9. api_credentials
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

        # Check and add new quality/metadata columns to documents table
        cursor.execute("PRAGMA table_info(documents)")
        existing_cols = {col["name"] for col in cursor.fetchall()}
        
        new_cols = {
            "overall_confidence": "REAL DEFAULT NULL",
            "confidence_level": "TEXT DEFAULT NULL",
            "is_blurry": "INTEGER DEFAULT 0",
            "has_ambiguous_fields": "INTEGER DEFAULT 0",
            "confidence_notes": "TEXT DEFAULT NULL",
            "review_priority": "TEXT DEFAULT NULL",
            "auto_approved": "INTEGER DEFAULT 0"
        }
        
        for col_name, col_type in new_cols.items():
            if col_name not in existing_cols:
                logger.info(f"Adding column '{col_name}' to 'documents' table...")
                cursor.execute(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}")

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
            ("EXTRACTED", "Extracted", "AI successfully extracted document payload to JSON file, waiting for DB insertion."),
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
        
        # 2. Discover and seed document sources from domain directory scans
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
    Returns list of domains from configs/document_domains.json.
    """
    json_path = "configs/document_domains.json"
    if not os.path.exists(json_path):
        logger.warning(f"Domain configuration file not found at: {json_path}")
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            domains = json.load(f)
        formatted_domains = []
        for d in domains:
            formatted_domains.append({
                "domain_id": d.get("domain_id"),
                "display_name": d.get("display_name"),
                "is_active": 1 if d.get("is_active", True) else 0,
                "sort_order": d.get("sort_order", 0)
            })
        formatted_domains.sort(key=lambda x: x["sort_order"])
        return formatted_domains
    except Exception as e:
        logger.error(f"Failed to load domains from JSON file: {e}")
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
    Toggles is_active for a domain inside configs/document_domains.json.
    """
    json_path = "configs/document_domains.json"
    if not os.path.exists(json_path):
        logger.error(f"Domain configuration file not found at: {json_path}")
        return False
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            domains = json.load(f)
            
        updated = False
        for d in domains:
            if d.get("domain_id") == domain_id:
                d["is_active"] = True if is_active == 1 else False
                updated = True
                break
                
        if updated:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(domains, f, ensure_ascii=False, indent=2)
            logger.info(f"Updated domain '{domain_id}' active status to {is_active == 1} in configs/document_domains.json")
            return True
        else:
            logger.warning(f"Domain '{domain_id}' not found in configs/document_domains.json")
            return False
    except Exception as e:
        logger.error(f"Failed to update domain active status in JSON file: {e}")
        return False

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

def get_merchants(conn: sqlite3.Connection = None) -> list[dict]:
    """
    Retrieves all merchants from merchant_master.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM merchant_master ORDER BY merchant_name ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to get merchants: {e}")
        return []
    finally:
        if should_close and conn:
            conn.close()

def upsert_merchant(merchant_id: str, tax_id: str, merchant_name: str,
                    default_wht_rate: float = 0.0, is_vat_registered: int = 1,
                    conn: sqlite3.Connection = None) -> bool:
    """
    Inserts or updates a merchant record in merchant_master.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        now_str = datetime.now().isoformat()
        
        # Check by merchant_id first
        cursor.execute("SELECT merchant_id FROM merchant_master WHERE merchant_id = ?", (merchant_id,))
        exists_by_id = cursor.fetchone()
        
        # Check by tax_id
        exists_by_tax = None
        if tax_id and tax_id.strip():
            cursor.execute("SELECT merchant_id FROM merchant_master WHERE tax_id = ?", (tax_id.strip(),))
            exists_by_tax = cursor.fetchone()
            
        if exists_by_id:
            cursor.execute("""
                UPDATE merchant_master
                SET tax_id = ?, merchant_name = ?, default_wht_rate = ?, is_vat_registered = ?, updated_at = ?
                WHERE merchant_id = ?
            """, (tax_id, merchant_name, default_wht_rate, is_vat_registered, now_str, merchant_id))
        elif exists_by_tax:
            cursor.execute("""
                UPDATE merchant_master
                SET merchant_name = ?, default_wht_rate = ?, is_vat_registered = ?, updated_at = ?
                WHERE tax_id = ?
            """, (merchant_name, default_wht_rate, is_vat_registered, now_str, tax_id))
        else:
            cursor.execute("""
                INSERT INTO merchant_master (merchant_id, tax_id, merchant_name, default_wht_rate, is_vat_registered, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (merchant_id, tax_id, merchant_name, default_wht_rate, is_vat_registered, now_str))
            
        if should_close:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to upsert merchant: {e}")
        return False
    finally:
        if should_close and conn:
            conn.close()

def match_merchant(tax_id: str, name: str, conn: sqlite3.Connection = None) -> str | None:
    """
    Matches a merchant from merchant_master by tax_id first, then by merchant_name.
    Returns merchant_id if matched, otherwise None.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        # 1. Match by Tax ID (exact match)
        if tax_id and tax_id.strip():
            cursor.execute("SELECT merchant_id FROM merchant_master WHERE tax_id = ?", (tax_id.strip(),))
            row = cursor.fetchone()
            if row:
                return row["merchant_id"]
        # 2. Match by Merchant Name (exact case-insensitive match)
        if name and name.strip():
            cursor.execute("SELECT merchant_id FROM merchant_master WHERE LOWER(merchant_name) = ?", (name.strip().lower(),))
            row = cursor.fetchone()
            if row:
                return row["merchant_id"]
    except Exception as e:
        logger.error(f"Error matching merchant: {e}")
    finally:
        if should_close and conn:
            conn.close()
    return None

def delete_merchant(merchant_id: str, conn: sqlite3.Connection = None) -> bool:
    """
    Deletes a merchant record from merchant_master.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM merchant_master WHERE merchant_id = ?", (merchant_id,))
        if should_close:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to delete merchant: {e}")
        return False
    finally:
        if should_close and conn:
            conn.close()

def insert_relational_receipt(document_id: str, payload: dict, original_filename: str, conn: sqlite3.Connection = None) -> bool:
    """
    Parses extracted JSON payload and inserts header and items into relational tables.
    Also auto-registers new merchants in merchant_master.
    """
    import uuid
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        now_str = datetime.now().isoformat()
        
        # 1. Extract merchant & receipt information with fallbacks
        merchant_obj = payload.get("merchant", {})
        receipt_info = payload.get("receipt_info", {})
        totals_obj = payload.get("totals", {}) or payload.get("financial_summary", {})

        merchant_name = merchant_obj.get("name") or payload.get("merchant_name")
        tax_id = merchant_obj.get("tax_id") or payload.get("tax_id")
        
        if not merchant_name:
            merchant_name = "Unknown Merchant"
        if tax_id:
            tax_id = tax_id.strip()
            
        # 2. Match merchant in merchant_master
        merchant_id = match_merchant(tax_id, merchant_name, conn=conn)
        if not merchant_id:
            merchant_id = f"mer_{uuid.uuid4().hex[:12]}"
            upsert_merchant(
                merchant_id=merchant_id,
                tax_id=tax_id,
                merchant_name=merchant_name,
                default_wht_rate=0.0,
                is_vat_registered=1,
                conn=conn
            )
            
        # 3. Clean up any existing receipt for this document_id (updates/re-runs)
        cursor.execute("SELECT receipt_id FROM expense_receipt WHERE document_id = ?", (document_id,))
        existing_receipt = cursor.fetchone()
        if existing_receipt:
            receipt_id = existing_receipt["receipt_id"]
            cursor.execute("DELETE FROM expense_receipt_d WHERE receipt_id = ?", (receipt_id,))
            cursor.execute("DELETE FROM expense_receipt WHERE receipt_id = ?", (receipt_id,))
        else:
            receipt_id = f"rcpt_{uuid.uuid4().hex[:12]}"
            
        # 4. Save Header
        subtotal = totals_obj.get("subtotal", 0.0)
        discount = totals_obj.get("discount", 0.0)
        vat_amount = totals_obj.get("vat_amount", 0.0)
        net_amount = totals_obj.get("net_amount", 0.0)
        
        transaction_date = receipt_info.get("transaction_date") or payload.get("transaction_date")
        expense_category = receipt_info.get("expense_category") or payload.get("expense_category")
        payment_method = receipt_info.get("payment_method") or payload.get("payment_method")

        cursor.execute("""
            INSERT INTO expense_receipt (
                receipt_id, document_id, merchant_id, transaction_date, merchant_name, tax_id,
                expense_category, subtotal, discount, vat_amount, net_amount, payment_method,
                source_file_name, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            receipt_id, document_id, merchant_id, transaction_date,
            merchant_name, tax_id, expense_category, subtotal,
            discount, vat_amount, net_amount, payment_method,
            original_filename, now_str
        ))
        
        # 5. Save Details (concatenated line items)
        for item in payload.get("items", []):
            item_id = f"itm_{uuid.uuid4().hex[:12]}"
            item_name = item.get("name")
            if not item_name:
                continue
            qty = item.get("qty", 1)
            unit_price = item.get("unit_price", 0.0)
            total_price = item.get("total_price", 0.0)
            
            cursor.execute("""
                INSERT INTO expense_receipt_d (item_id, receipt_id, item_name, qty, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (item_id, receipt_id, item_name, qty, unit_price, total_price))
            
        if should_close:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to insert relational receipt for doc '{document_id}': {e}")
        if should_close and conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return False
    finally:
        if should_close and conn:
            conn.close()
