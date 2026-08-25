"""
Package-Level Pytest Configuration for Integration Tests.
Initializes database schema and seeds initial data exclusively when running integration test suites.
"""

import pytest
from src.infrastructure.persistence.schema import initialize_db_schema
from src.infrastructure.persistence.seeder import seed_initial_data


@pytest.fixture(scope="package", autouse=True)
def integration_test_database_setup():
    """
    Package-level fixture that initializes schema and seeds initial master data
    in the isolated temporary session database exclusively for integration tests.
    """
    try:
        initialize_db_schema()
        seed_initial_data()
    except Exception as e:
        from src.infrastructure.common.logger import logger
        logger.warning(f"Warning during integration test DB setup: {e}")

    yield
