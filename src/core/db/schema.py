import os
import json
from loguru import logger
from .connection import get_db_connection, get_log_db_connection

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
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                overall_confidence REAL,
                confidence_level TEXT,
                is_blurry INTEGER,
                has_ambiguous_fields INTEGER,
                confidence_notes TEXT,
                review_priority TEXT,
                auto_approved INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (batch_id) REFERENCES processed_batches(batch_id) ON DELETE CASCADE,
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
                FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE SET NULL,
                FOREIGN KEY (status_code) REFERENCES document_statuses(status_code)
            )
        """)
        
        # 6. api_credentials
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
        
        # 7. merchant_master
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS merchant_master (
                merchant_id TEXT PRIMARY KEY,
                tax_id TEXT,
                merchant_name TEXT NOT NULL,
                default_wht_rate REAL DEFAULT 0.0,
                is_vat_registered INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_merchant_tax_id ON merchant_master(tax_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_merchant_name ON merchant_master(merchant_name);")
        
        # 8. expense_receipt
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expense_receipt (
                receipt_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                merchant_id TEXT NOT NULL,
                transaction_date TEXT,
                merchant_name TEXT,
                tax_id TEXT,
                expense_category TEXT,
                subtotal REAL DEFAULT 0.0,
                discount REAL DEFAULT 0.0,
                vat_amount REAL DEFAULT 0.0,
                net_amount REAL DEFAULT 0.0,
                payment_method TEXT,
                source_file_name TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
                FOREIGN KEY (merchant_id) REFERENCES merchant_master(merchant_id)
            )
        """)
        
        # 9. expense_receipt_d
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expense_receipt_d (
                item_id TEXT PRIMARY KEY,
                receipt_id TEXT NOT NULL,
                item_name TEXT NOT NULL,
                qty REAL DEFAULT 1.0,
                unit_price REAL DEFAULT 0.0,
                total_price REAL DEFAULT 0.0,
                FOREIGN KEY (receipt_id) REFERENCES expense_receipt(receipt_id) ON DELETE CASCADE
            )
        """)
        
        # 10. api_call_logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_call_logs (
                log_id TEXT PRIMARY KEY,
                batch_id TEXT,
                credential_id TEXT,
                provider TEXT NOT NULL,
                model_name TEXT NOT NULL,
                chunk_index INTEGER,
                request_pages TEXT,
                status TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                latency_ms REAL,
                error_reason TEXT,
                raw_response TEXT,
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
    Seeds statuses, discoverable sources, and default API credentials.
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
            ("NEEDS_REVIEW", "Needs Review", "Document requires manual review before approval."),
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
                                Cartesian
                                """.replace("Cartesian", ""), (entry, domain_id, display_name, 1))
                                
        # 3. Seed default API credentials
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

def reset_pipeline_database(clear_documents_only: bool = True) -> dict:
    """
    Safely resets pipeline database.
    If clear_documents_only is True, clears transactional tables (expense_receipt_d,
    expense_receipt, document_pages, documents, processed_batches, api_call_logs)
    while preserving master sources and statuses.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        tables_to_clear = [
            "expense_receipt_d",
            "expense_receipt",
            "document_pages",
            "documents",
            "processed_batches",
            "api_call_logs"
        ]
        
        deleted_counts = {}
        for table in tables_to_clear:
            try:
                cursor.execute(f"DELETE FROM {table}")
                deleted_counts[table] = cursor.rowcount
            except Exception as te:
                logger.warning(f"Could not clear table {table}: {te}")
                
        conn.commit()
        # Vacuum database to reclaim space outside transaction
        try:
            conn.isolation_level = None
            cursor.execute("VACUUM")
        except Exception as ve:
            logger.debug(f"VACUUM note: {ve}")
            
        logger.info(f"Pipeline database reset successfully. Cleared tables: {list(deleted_counts.keys())}")
        return {"success": True, "deleted_counts": deleted_counts}
    except Exception as e:
        logger.error(f"Error resetting pipeline database: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if conn:
            conn.close()

