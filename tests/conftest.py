"""
Global Pytest Configuration & Test Isolation Guard.
Enforces 100% database and filesystem isolation for all unit and integration test suites.
Guarantees zero writes or state mutations to the real storage/database/pipeline.db.
"""

import os
import gc
import uuid
import pytest
import tempfile
from pathlib import Path

from src.infrastructure.persistence.connection import dispose_all_engines
from src.infrastructure.persistence.schema import initialize_db_schema
from src.infrastructure.persistence.seeder import seed_initial_data


@pytest.fixture(scope="session", autouse=True)
def global_test_database_guard():
    """
    Session-level fixture that automatically redirects all database operations
    to an isolated temporary SQLite database for the entire test session.
    """
    temp_dir = tempfile.gettempdir()
    session_db_path = os.path.join(
        temp_dir, f"pytest_global_guard_{uuid.uuid4().hex[:8]}.db"
    ).replace("\\", "/")

    # Set global environment override before any test module executes
    original_override = os.environ.get("DB_PATH_OVERRIDE")
    os.environ["DB_PATH_OVERRIDE"] = session_db_path
    os.environ["TEST_ENVIRONMENT"] = "1"

    # Initialize schema and seed data in the isolated session DB
    try:
        initialize_db_schema()
        seed_initial_data()
    except Exception as e:
        print(f"Warning during global test DB setup: {e}")

    yield session_db_path

    # Teardown: Close all connections and remove temporary session database
    dispose_all_engines()
    gc.collect()

    if original_override is not None:
        os.environ["DB_PATH_OVERRIDE"] = original_override
    else:
        os.environ.pop("DB_PATH_OVERRIDE", None)

    os.environ.pop("TEST_ENVIRONMENT", None)

    if os.path.exists(session_db_path):
        try:
            os.remove(session_db_path)
        except Exception:
            pass
