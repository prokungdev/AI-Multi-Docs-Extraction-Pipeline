import os
import json
import sqlite3
import hashlib
from datetime import datetime
from loguru import logger

def get_db_connection(settings_path: str = "configs/settings.json") -> sqlite3.Connection:
    """
    Establishes a connection to the centralized SQLite database.
    The database path is resolved dynamically using 'storage_root' from settings.json.
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
    db_path = os.path.join(storage_root, "pipeline.db").replace("\\", "/")
    
    conn = sqlite3.connect(db_path)
    return conn

def initialize_database():
    """
    Initializes the database schema and creates tables if they do not exist.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_documents (
                file_hash TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                filename TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                processed_at TEXT
            )
        """)
        conn.commit()
        logger.info("Centralized SQLite database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database: {e}")
        raise e
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
    Checks if a document with the given SHA-256 hash has already been processed.
    
    Returns:
        A tuple of (is_duplicate: bool, metadata: dict | None)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT domain, filename, source, status, created_at, processed_at FROM processed_documents WHERE file_hash = ?",
            (file_hash,)
        )
        row = cursor.fetchone()
        if row:
            metadata = {
                "domain": row[0],
                "filename": row[1],
                "source": row[2],
                "status": row[3],
                "created_at": row[4],
                "processed_at": row[5]
            }
            return True, metadata
    except Exception as e:
        logger.error(f"Failed to check duplicate document in DB: {e}")
    finally:
        if conn:
            conn.close()
            
    return False, None

def insert_pending_document(file_hash: str, domain: str, filename: str, source: str):
    """
    Inserts a new document record into the database with an 'in_progress' status.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        created_at = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT OR REPLACE INTO processed_documents (file_hash, domain, filename, source, status, created_at)
            VALUES (?, ?, ?, ?, 'in_progress', ?)
            """,
            (file_hash, domain, filename, source, created_at)
        )
        conn.commit()
        logger.info(f"Document hash '{file_hash}' recorded in DB with status 'in_progress'.")
    except Exception as e:
        logger.error(f"Failed to insert pending document in DB: {e}")
    finally:
        if conn:
            conn.close()

def update_document_to_archived(file_hash: str, domain: str, source: str):
    """
    Updates the document status to 'archived' and records the processed timestamp.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        processed_at = datetime.now().isoformat()
        cursor.execute(
            """
            UPDATE processed_documents
            SET status = 'archived', source = ?, processed_at = ?
            WHERE file_hash = ? AND domain = ?
            """,
            (source, processed_at, file_hash, domain)
        )
        conn.commit()
        logger.info(f"Document hash '{file_hash}' status updated to 'archived' in DB.")
    except Exception as e:
        logger.error(f"Failed to update document status to archived in DB: {e}")
    finally:
        if conn:
            conn.close()
