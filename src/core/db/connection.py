"""Database connection and SQLAlchemy Engine / Session management.

Resolves connection URLs dynamically for SQLite (default) and PostgreSQL (production).
"""

import os
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Project root directory (4 levels up from src/core/db/connection.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

def get_database_url(settings_path: str = "configs/settings.json") -> str:
    """
    Resolves database connection URL dynamically.
    Prioritizes DB_URL_OVERRIDE or DB_PATH_OVERRIDE environment variables, falls back to SQLite file.
    """
    env_url = os.environ.get("DB_URL_OVERRIDE")
    if env_url:
        return env_url

    override_path = os.environ.get("DB_PATH_OVERRIDE")
    if override_path:
        return f"sqlite:///{override_path.replace('\\', '/')}"

    abs_settings_path = PROJECT_ROOT / settings_path if not os.path.isabs(settings_path) else Path(settings_path)
    storage_root = "pipeline_storage"
    if abs_settings_path.exists():
        try:
            with open(abs_settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            storage_root = settings.get("storage_root", "pipeline_storage")
        except Exception as e:
            logger.warning(f"Failed to read settings.json for DB URL resolution: {e}")

    abs_storage_dir = PROJECT_ROOT / storage_root if not os.path.isabs(storage_root) else Path(storage_root)
    os.makedirs(abs_storage_dir, exist_ok=True)
    db_path = str((abs_storage_dir / "pipeline.db").resolve()).replace("\\", "/")
    return f"sqlite:///{db_path}"

def get_engine():
    """
    Returns an Engine instance for the currently resolved DATABASE_URL.
    """
    url = get_database_url()
    is_sqlite = url.startswith("sqlite")
    return create_engine(
        url,
        connect_args={"check_same_thread": False} if is_sqlite else {},
        echo=False
    )

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for SQLAlchemy ORM sessions.
    Automatically commits transactions, rolls back on exception, and closes session.
    """
    current_engine = get_engine()
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=current_engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_db_connection(settings_path: str = "configs/settings.json") -> sqlite3.Connection:
    """
    Legacy helper: Establishes a raw connection to the centralized SQLite database.
    """
    db_url = get_database_url(settings_path)
    if db_url.startswith("sqlite:///"):
        raw_path = db_url.replace("sqlite:///", "")
    else:
        raw_path = "pipeline_storage/pipeline.db"

    conn = sqlite3.connect(raw_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def get_log_db_connection(settings_path: str = "configs/settings.json") -> sqlite3.Connection:
    """
    Establishes a connection to the separate logs SQLite database (logs/logs.db).
    """
    abs_settings_path = PROJECT_ROOT / settings_path if not os.path.isabs(settings_path) else Path(settings_path)
    logs_dir = "logs"
    if abs_settings_path.exists():
        try:
            with open(abs_settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            logging_cfg = settings.get("logging", {})
            logs_dir = logging_cfg.get("logs_dir", "logs")
        except Exception:
            pass

    abs_logs_dir = PROJECT_ROOT / logs_dir if not os.path.isabs(logs_dir) else Path(logs_dir)
    os.makedirs(abs_logs_dir, exist_ok=True)
    db_path = str((abs_logs_dir / "logs.db").resolve()).replace("\\", "/")

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db_connection_ctx(settings_path: str = "configs/settings.json") -> Generator[sqlite3.Connection, None, None]:
    """
    Legacy context manager for database connections with automatic commit, rollback on error, and closure.
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
    Legacy context manager for log database connections with automatic commit, rollback on error, and closure.
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

