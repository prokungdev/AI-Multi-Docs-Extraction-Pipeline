"""Database connection and SQLAlchemy Engine / Session management.

Resolves connection URLs and pools dynamically for SQLite (default) and PostgreSQL (production)
based on central settings.json and environment configurations.
"""

import os
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator
from src.infrastructure.common.logger import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.infrastructure.common.constants import DefaultPath

# Project root directory (4 levels up from src/core/db/connection.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def get_database_config(settings_path: str = DefaultPath.SETTINGS) -> dict:
    """
    Loads the database configuration block from settings.json.
    """
    abs_settings_path = PROJECT_ROOT / settings_path if not os.path.isabs(settings_path) else Path(settings_path)
    if abs_settings_path.exists():
        try:
            with open(abs_settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            return settings.get("database", {})
        except Exception as e:
            logger.warning(f"Failed to read database configuration from {settings_path}: {e}")
    return {}


def get_database_url(settings_path: str = DefaultPath.SETTINGS) -> str:
    """
    Resolves database connection URL dynamically.
    Priority:
      1. DB_URL_OVERRIDE / DB_PATH_OVERRIDE (unit test mock overrides)
      2. If active_driver == 'postgresql': reads url_env (e.g. DATABASE_URL from .env)
      3. If active_driver == 'sqlite': resolves {storage_root}/{db_filename}
    """
    env_url = os.environ.get("DB_URL_OVERRIDE")
    if env_url:
        return env_url

    override_path = os.environ.get("DB_PATH_OVERRIDE")
    if override_path:
        return f"sqlite:///{override_path.replace('\\', '/')}"

    if os.environ.get("TEST_ENVIRONMENT") == "1":
        import tempfile
        fallback_test_db = os.path.join(tempfile.gettempdir(), "pytest_fail_safe_guard.db").replace("\\", "/")
        return f"sqlite:///{fallback_test_db}"

    abs_settings_path = PROJECT_ROOT / settings_path if not os.path.isabs(settings_path) else Path(settings_path)
    settings = {}
    storage_root = "storage"
    if abs_settings_path.exists():
        try:
            with open(abs_settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            storage_root = settings.get("storage_root", "storage")
        except Exception as e:
            logger.warning(f"Failed to read settings.json for DB URL resolution: {e}")

    db_cfg = settings.get("database", {})
    active_driver = db_cfg.get("active_driver", "sqlite").lower()

    if active_driver == "postgresql":
        pg_cfg = db_cfg.get("postgresql", {})
        url_env_name = pg_cfg.get("url_env", "DATABASE_URL")
        pg_url = os.environ.get(url_env_name)
        if pg_url:
            return pg_url
        logger.warning(f"PostgreSQL active driver selected but environment variable '{url_env_name}' is not set. Falling back to SQLite.")

    # SQLite resolution (Default)
    sqlite_cfg = db_cfg.get("sqlite", {})
    db_filename = sqlite_cfg.get("db_filename", "database/pipeline.db")
    abs_storage_dir = PROJECT_ROOT / storage_root if not os.path.isabs(storage_root) else Path(storage_root)
    full_db_path = (abs_storage_dir / db_filename).resolve()
    os.makedirs(full_db_path.parent, exist_ok=True)
    db_path = str(full_db_path).replace("\\", "/")
    return f"sqlite:///{db_path}"


_engines: dict = {}
_session_factories: dict = {}


from sqlalchemy import event, Engine

@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Auto-enables WAL mode and foreign key constraints on SQLite connections."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


def dispose_all_engines():
    """Disposes all cached engines and clears session factories (Used for clean test teardown)."""
    global _engines, _session_factories
    for eng in _engines.values():
        try:
            eng.dispose()
        except Exception:
            pass
    _engines.clear()
    _session_factories.clear()


def get_engine(settings_path: str = DefaultPath.SETTINGS):
    """
    Returns a cached Engine instance per database URL with connection pooling.
    Guarantees pool reuse in production while maintaining test DB isolation.
    """
    url = get_database_url(settings_path)
    if url in _engines:
        return _engines[url]

    db_cfg = get_database_config(settings_path)
    echo_sql = db_cfg.get("echo_sql", False)

    if url.startswith("sqlite"):
        new_engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=echo_sql
        )
    else:
        # PostgreSQL / MySQL enterprise connection pooling
        pg_cfg = db_cfg.get("postgresql", {})
        pool_size = pg_cfg.get("pool_size", 10)
        max_overflow = pg_cfg.get("max_overflow", 20)
        pool_recycle = pg_cfg.get("pool_recycle", 3600)
        pool_pre_ping = pg_cfg.get("pool_pre_ping", True)

        new_engine = create_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            echo=echo_sql
        )

    _engines[url] = new_engine
    return new_engine


def get_session_factory(settings_path: str = DefaultPath.SETTINGS) -> sessionmaker:
    """Returns a cached sessionmaker factory for the active database engine."""
    url = get_database_url(settings_path)
    if url not in _session_factories:
        eng = get_engine(settings_path)
        _session_factories[url] = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    return _session_factories[url]


engine = get_engine()
SessionLocal = get_session_factory()


@contextmanager
def get_db_session(settings_path: str = DefaultPath.SETTINGS) -> Generator[Session, None, None]:
    """
    Context manager for SQLAlchemy ORM sessions.
    Reuses connection pool per database URL (zero pool churn in production).
    Automatically commits transactions, rolls back on exception, and closes session.
    """
    factory = get_session_factory(settings_path)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session_dep() -> Generator[Session, None, None]:
    """
    FastAPI Dependency for transactional SQLAlchemy ORM sessions.
    Automatically commits on success, rolls back on exception, and ensures safe cleanup.
    """
    with get_db_session() as session:
        yield session


def get_db_connection(settings_path: str = DefaultPath.SETTINGS) -> sqlite3.Connection:
    """
    Legacy helper: Establishes a raw connection to the centralized SQLite database.
    """
    db_url = get_database_url(settings_path)
    if db_url.startswith("sqlite:///"):
        raw_path = db_url.replace("sqlite:///", "")
    else:
        raw_path = "storage/database/pipeline.db"

    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    conn = sqlite3.connect(raw_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def get_log_database_url(settings_path: str = DefaultPath.SETTINGS) -> str:
    """
    Resolves log database connection URL pointing to logs/logs.db.
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
    return f"sqlite:///{db_path}"


def get_log_engine(settings_path: str = DefaultPath.SETTINGS):
    """
    Returns a cached Engine instance for the log database (logs/logs.db).
    """
    url = get_log_database_url(settings_path)
    if url in _engines:
        return _engines[url]

    new_engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        echo=False
    )
    _engines[url] = new_engine
    return new_engine


def get_log_session_factory(settings_path: str = DefaultPath.SETTINGS) -> sessionmaker:
    """Returns a cached sessionmaker factory for the log database engine."""
    url = get_log_database_url(settings_path)
    if url not in _session_factories:
        eng = get_log_engine(settings_path)
        _session_factories[url] = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    return _session_factories[url]


log_engine = get_log_engine()
LogSessionLocal = get_log_session_factory()


@contextmanager
def get_log_db_session(settings_path: str = DefaultPath.SETTINGS) -> Generator[Session, None, None]:
    """
    Context manager for SQLAlchemy ORM sessions on the log database (logs/logs.db).
    Automatically commits transactions, rolls back on exception, and closes session.
    """
    factory = get_log_session_factory(settings_path)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_log_db_connection(settings_path: str = DefaultPath.SETTINGS) -> sqlite3.Connection:
    """
    Legacy helper: Establishes a raw connection to the separate logs SQLite database (logs/logs.db).
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
    db_path = str((abs_logs_dir / "logs.db").resolve())

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db_connection_ctx(settings_path: str = DefaultPath.SETTINGS) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections that automatically handles closing.
    """
    conn = get_db_connection(settings_path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_log_db_connection_ctx(settings_path: str = DefaultPath.SETTINGS) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for log database connections that automatically handles closing.
    """
    conn = get_log_db_connection(settings_path)
    try:
        yield conn
    finally:
        conn.close()
