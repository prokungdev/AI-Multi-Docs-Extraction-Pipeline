"""Database schema initialization and seeding routines using SQLAlchemy.
"""

import os
import json
from pathlib import Path
from loguru import logger
from .connection import engine, get_engine, get_db_connection, get_log_db_connection, PROJECT_ROOT
from .models import (
    Base,
    DocumentStatus,
    DocumentSource,
    ApiCredential
)

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
    Creates relational database schema for all models via SQLAlchemy Base Metadata.
    """
    try:
        current_engine = get_engine()
        Base.metadata.create_all(current_engine)
        logger.info("Relational database schema initialized successfully via SQLAlchemy Base metadata.")
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        raise e

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
        abs_configs_dir = PROJECT_ROOT / configs_dir if not os.path.isabs(configs_dir) else Path(configs_dir)
        domains_dir = str(abs_configs_dir / "domains")
        if os.path.exists(domains_dir):
            for domain_id in os.listdir(domains_dir):
                domain_path = os.path.join(domains_dir, domain_id)
                if os.path.isdir(domain_path):
                    sources_dir = os.path.join(domain_path, "sources")
                    if os.path.exists(sources_dir):
                        cursor.execute("""
                            INSERT OR IGNORE INTO document_sources (source_id, domain_id, display_name, is_active)
                            VALUES (?, ?, ?, ?)
                        """, ("_default", domain_id, "Default Fallback", 1))
                        
                        for entry in os.listdir(sources_dir):
                            entry_path = os.path.join(sources_dir, entry)
                            if os.path.isdir(entry_path) and not entry.startswith("_"):
                                display_name = entry.replace("_", " ").title()
                                cursor.execute("""
                                    INSERT OR IGNORE INTO document_sources (source_id, domain_id, display_name, is_active)
                                    VALUES (?, ?, ?, ?)
                                """, (entry, domain_id, display_name, 1))
                                
        # 3. Seed default API credentials
        cursor.execute("""
            INSERT OR IGNORE INTO api_credentials (credential_id, provider, model_name, api_key_env, is_active, last_active_at, error_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("cred_gemini_default", "gemini", "gemini-3.5-flash", "GEMINI_API_KEY", 1, None, 0))
                                
        conn.commit()
        logger.info("Database seeding completed.")
    except Exception as e:
        logger.error(f"Failed to seed database: {e}")
    finally:
        if conn:
            conn.close()

def reset_pipeline_database(clear_documents_only: bool = True) -> dict:
    """
    Safely resets pipeline database tables.
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
