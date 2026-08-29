"""
Unit tests for AppLogger Universal Logging Gateway and ApiCallLogCreate DTO.
Validates structured log bindings, level forwarding, and DTO validations without DB I/O.
"""

import uuid
import pytest
from src.infrastructure.core.logger import logger, get_logger, AppLogger
from src.infrastructure.core.telemetry import ApiCallLogCreate


def test_app_logger_gateway_and_binding():
    """Test that AppLogger gateway delegates standard logging levels without error."""
    # Arrange
    assert isinstance(logger, AppLogger)

    # Act & Assert
    logger.debug("Test debug message")
    logger.info("Test info message")
    logger.warning("Test warning message")
    logger.error("Test error message")

    bound = logger.bind(custom_tag="unit_test")
    assert isinstance(bound, AppLogger)
    bound.info("Test bound logger message")

    mod_logger = get_logger("test_module")
    assert isinstance(mod_logger, AppLogger)


def test_audit_log_dto_validation():
    """Test ApiCallLogCreate DTO construction and validation without database write."""
    # Arrange & Act
    dto = ApiCallLogCreate(
        log_id=f"test_{uuid.uuid4().hex[:8]}",
        batch_id="batch_unit_test",
        provider="test_provider",
        model_name="test_model",
        status_code="SUCCESS",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001
    )

    # Assert
    assert dto.provider == "test_provider"
    assert dto.input_tokens == 100
    assert dto.output_tokens == 50
    assert dto.cost_usd == 0.001
