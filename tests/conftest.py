"""
Global Pytest Configuration & Test Isolation Guard.
Enforces 100% database and filesystem isolation for all unit and integration test suites.
Guarantees zero writes or state mutations to the real storage/database/pipeline.db.
"""

import os
import sys
import gc
import uuid
import pytest
import tempfile
from pathlib import Path

# Ensure project root is in sys.path for test discovery
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.infrastructure.persistence.connection import dispose_all_engines
from src.infrastructure.common.logger import setup_logger


@pytest.fixture(scope="session", autouse=True)
def global_test_database_guard():
    """
    Session-level safety fixture that automatically redirects all database operations
    to an isolated temporary SQLite database for the entire test session.
    Guarantees 100% zero DB leakage to production pipeline.db.
    """
    temp_dir = tempfile.gettempdir()
    session_db_path = os.path.join(
        temp_dir, f"pytest_global_guard_{uuid.uuid4().hex[:8]}.db"
    ).replace("\\", "/")

    # Set global environment override before any test module executes
    original_override = os.environ.get("DB_PATH_OVERRIDE")
    original_test_env = os.environ.get("TEST_ENVIRONMENT")
    original_app_env = os.environ.get("APP_ENV")

    os.environ["DB_PATH_OVERRIDE"] = session_db_path
    os.environ["TEST_ENVIRONMENT"] = "1"
    os.environ["APP_ENV"] = "testing"

    # Re-initialize logger to register test environment settings (bypassing DB sink)
    setup_logger()

    yield session_db_path

    # Teardown: Close all connections and remove temporary session database
    dispose_all_engines()
    gc.collect()

    if original_override is not None:
        os.environ["DB_PATH_OVERRIDE"] = original_override
    else:
        os.environ.pop("DB_PATH_OVERRIDE", None)

    if original_test_env is not None:
        os.environ["TEST_ENVIRONMENT"] = original_test_env
    else:
        os.environ.pop("TEST_ENVIRONMENT", None)

    if original_app_env is not None:
        os.environ["APP_ENV"] = original_app_env
    else:
        os.environ.pop("APP_ENV", None)

    if os.path.exists(session_db_path):
        try:
            os.remove(session_db_path)
        except Exception:
            pass


@pytest.fixture(scope="session", autouse=True)
def global_test_storage_guard():
    """
    Session-level safety fixture that automatically redirects all storage filesystem operations
    to an isolated temporary directory for the entire test session.
    Guarantees 100% zero file leakage into the production storage/ tree and deletes all files upon completion.
    """
    import shutil
    test_storage_dir = tempfile.mkdtemp(prefix="pytest_storage_").replace("\\", "/")
    original_storage_override = os.environ.get("STORAGE_ROOT_OVERRIDE")
    os.environ["STORAGE_ROOT_OVERRIDE"] = test_storage_dir

    yield test_storage_dir

    # Teardown: Clean up isolated storage directory completely
    if original_storage_override is not None:
        os.environ["STORAGE_ROOT_OVERRIDE"] = original_storage_override
    else:
        os.environ.pop("STORAGE_ROOT_OVERRIDE", None)

    if os.path.exists(test_storage_dir):
        shutil.rmtree(test_storage_dir, ignore_errors=True)

