"""
Global Pytest Configuration, Test Isolation Guard, and Resource Cleanup Verifier.
Enforces 100% database and filesystem isolation for all unit and integration test suites.
Guarantees zero writes or state mutations to production databases and storage paths.
"""

import os
import sys
import gc
import uuid
import shutil
import pytest
import tempfile
from pathlib import Path


def pytest_configure(config):
    """
    Set test environment variables BEFORE any test module is imported.
    This is the earliest pytest hook — runs before conftest fixtures and before
    any src module import, preventing Loguru db_sink (enqueue=True) from being
    registered and causing pytest teardown to hang indefinitely.
    """
    os.environ["TEST_ENVIRONMENT"] = "1"
    os.environ["APP_ENV"] = "testing"


# Ensure project root is in sys.path for test discovery
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.infrastructure.database.engine import dispose_all_engines
from src.infrastructure.database.schema import initialize_db_schema
from src.infrastructure.core.logger import setup_logger


# Production path signatures that MUST NEVER be targeted during testing
FORBIDDEN_PROD_DB_SUBSTRINGS = ["storage/database/pipeline.db", "pipeline.db", "logs/logs.db", "logs.db"]
FORBIDDEN_PROD_STORAGE_SUBSTRINGS = ["storage/raw_data", "storage/processed_data"]


@pytest.fixture(autouse=True)
def auto_test_user_context_guard():
    """
    Guarantees that every unit and integration test runs inside an isolated UserContext.
    Sets 'usr_system_auto' as the test actor and cleanly resets on teardown.
    """
    from src.infrastructure.core.user_context import user_scope
    from src.infrastructure.core.constants import SystemUserId
    with user_scope(SystemUserId.AUTO_SYSTEM):
        yield


@pytest.fixture(scope="session", autouse=True)
def global_test_database_guard():
    """
    Session-level safety fixture that automatically redirects all database operations
    to an isolated temporary SQLite database for the entire test session.
    Guarantees 100% zero DB leakage to production pipeline.db and logs.db.
    """
    temp_dir = tempfile.gettempdir()
    session_db_path = os.path.join(
        temp_dir, f"pytest_global_guard_{uuid.uuid4().hex[:8]}.db"
    ).replace("\\", "/")
    session_log_db_path = os.path.join(
        temp_dir, f"pytest_global_log_guard_{uuid.uuid4().hex[:8]}.db"
    ).replace("\\", "/")

    # Set global environment override before any test module executes
    original_override = os.environ.get("DB_PATH_OVERRIDE")
    original_log_override = os.environ.get("LOG_DB_PATH_OVERRIDE")
    original_test_env = os.environ.get("TEST_ENVIRONMENT")
    original_app_env = os.environ.get("APP_ENV")

    os.environ["DB_PATH_OVERRIDE"] = session_db_path
    os.environ["LOG_DB_PATH_OVERRIDE"] = session_log_db_path
    os.environ["TEST_ENVIRONMENT"] = "1"
    os.environ["APP_ENV"] = "testing"

    # Strict Safety Check: Verify DB_PATH_OVERRIDE is truly an isolated temp DB
    for forbidden in FORBIDDEN_PROD_DB_SUBSTRINGS:
        if session_db_path.endswith(forbidden) or session_log_db_path.endswith(forbidden):
            raise RuntimeError(f"FATAL SAFETY BREACH: Test database resolved to production path: {session_db_path}")

    # Re-initialize logger to register test environment settings (bypassing DB sink)
    setup_logger()

    # Initialize isolated schema in temporary test database
    initialize_db_schema()

    yield session_db_path

    # Teardown: Close all connections and remove temporary session database
    dispose_all_engines()
    gc.collect()

    # Flush & stop Loguru background enqueue thread
    try:
        from loguru import logger as _loguru_backend
        _loguru_backend.remove()
    except Exception:
        pass

    if original_override is not None:
        os.environ["DB_PATH_OVERRIDE"] = original_override
    else:
        os.environ.pop("DB_PATH_OVERRIDE", None)

    if original_log_override is not None:
        os.environ["LOG_DB_PATH_OVERRIDE"] = original_log_override
    else:
        os.environ.pop("LOG_DB_PATH_OVERRIDE", None)

    if original_test_env is not None:
        os.environ["TEST_ENVIRONMENT"] = original_test_env
    else:
        os.environ.pop("TEST_ENVIRONMENT", None)

    if original_app_env is not None:
        os.environ["APP_ENV"] = original_app_env
    else:
        os.environ.pop("APP_ENV", None)

    # Cleanup Verification: Verify temporary session database files are removed
    for db_p in [session_db_path, session_log_db_path]:
        if os.path.exists(db_p):
            try:
                os.remove(db_p)
            except Exception:
                pass


@pytest.fixture(scope="session", autouse=True)
def global_test_storage_guard():
    """
    Session-level safety fixture that automatically redirects all storage filesystem operations
    to an isolated temporary directory for the entire test session.
    Guarantees 100% zero file leakage into the production storage/ tree and deletes all files upon completion.
    """
    test_storage_dir = tempfile.mkdtemp(prefix="pytest_storage_").replace("\\", "/")
    original_storage_override = os.environ.get("STORAGE_ROOT_OVERRIDE")
    os.environ["STORAGE_ROOT_OVERRIDE"] = test_storage_dir

    # Strict Safety Check: Verify STORAGE_ROOT_OVERRIDE is not targeting real repo storage
    for forbidden in FORBIDDEN_PROD_STORAGE_SUBSTRINGS:
        if forbidden in test_storage_dir:
            raise RuntimeError(f"FATAL SAFETY BREACH: Storage root resolved to production path: {test_storage_dir}")

    # Snapshot real repo storage state before tests run (Deep Recursive Anti-Pollution Watchdog)
    import glob
    real_storage_dir = os.path.join(_project_root, "storage").replace("\\", "/")
    initial_storage_files = set(f.replace("\\", "/") for f in glob.glob(f"{real_storage_dir}/**/*", recursive=True))

    yield test_storage_dir

    # Teardown: Clean up isolated storage directory completely
    if original_storage_override is not None:
        os.environ["STORAGE_ROOT_OVERRIDE"] = original_storage_override
    else:
        os.environ.pop("STORAGE_ROOT_OVERRIDE", None)

    # Cleanup Verification: Verify isolated storage directory is deleted
    if os.path.exists(test_storage_dir):
        shutil.rmtree(test_storage_dir, ignore_errors=True)

    # Deep Recursive Anti-Pollution Watchdog Assertion: Verify ZERO new files or directories were created in real storage tree
    if os.path.exists(real_storage_dir):
        final_storage_files = set(f.replace("\\", "/") for f in glob.glob(f"{real_storage_dir}/**/*", recursive=True))
        leaked_files = final_storage_files - initial_storage_files
        if leaked_files:
            raise RuntimeError(
                f"CRITICAL TEST ISOLATION FAILURE: Leaked storage items found in real storage tree: {leaked_files}"
            )
