import os
import json
import sqlite3
from contextlib import contextmanager
from typing import Generator
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

@contextmanager
def get_db_connection_ctx(settings_path: str = "configs/settings.json") -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections with automatic commit, rollback on error, and closure.
    """
    conn = get_db_connection(settings_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@contextmanager
def get_log_db_connection_ctx(settings_path: str = "configs/settings.json") -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for log database connections with automatic commit, rollback on error, and closure.
    """
    conn = get_log_db_connection(settings_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
