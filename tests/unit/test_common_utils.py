"""
Unit tests for shared common utilities, helpers, and pure functions.
Uses pytest parameterization and standard AAA pattern.
"""

import os
import tempfile
import uuid
import pytest

from src.domain.services.post_processor import normalize_date_to_ad
from src.infrastructure.common.utils import chunk_list
from src.infrastructure.persistence.documents import calculate_file_hash
from src.infrastructure.persistence.masters import sanitize_short_name
from src.infrastructure.common.logger import logger, get_logger, AppLogger
from src.infrastructure.persistence.logs import ApiCallLogCreate, AuditLogService
from src.infrastructure.pdf.pdf_service import PDFService


# ==============================================================================
# Date Normalization Tests (Buddhist Era -> Christian Era)
# ==============================================================================

@pytest.mark.parametrize("input_date, expected", [
    ("2567-05-15", "2024-05-15"),
    ("2568/12/31", "2025-12-31"),
    ("15/05/2567", "2024-05-15"),
    ("01-01-2566", "2023-01-01"),
    ("2024-05-15", "2024-05-15"),
    ("15/05/2024", "2024-05-15"),
    ("2500-01-01", "2500-01-01"),
    ("2501-01-01", "1958-01-01"),
    ("", ""),
    (None, ""),
    ("   ", ""),
    ("invalid-date-string", "invalid-date-string"),
])
def test_date_normalization_parameterized(input_date, expected):
    """Test date normalization handles BE/AD, formats, boundaries, and empty strings."""
    # Arrange & Act
    actual = normalize_date_to_ad(input_date)
    # Assert
    assert actual == expected


# ==============================================================================
# List Chunking Utility Tests
# ==============================================================================

@pytest.mark.parametrize("input_list, chunk_sz, expected", [
    ([1, 2, 3, 4, 5, 6], 2, [[1, 2], [3, 4], [5, 6]]),
    (["a", "b", "c", "d", "e"], 2, [["a", "b"], ["c", "d"], ["e"]]),
    ([], 5, []),
    ([1, 2, 3], 0, [[1, 2, 3]]),
    ([1, 2, 3], -1, [[1, 2, 3]]),
])
def test_list_chunking_parameterized(input_list, chunk_sz, expected):
    """Test chunk_list divides lists evenly, handles remainders, and manages invalid chunk sizes."""
    # Arrange & Act
    actual = chunk_list(input_list, chunk_sz)
    # Assert
    assert actual == expected


# ==============================================================================
# String Sanitization Tests
# ==============================================================================

@pytest.mark.parametrize("input_name, expected", [
    ("7ELEVEN", "7eleven"),
    ("Big C Supercenter", "big_c_supercenter"),
    ("HomePro (HQ) #001", "homepro_hq_001"),
    ("", "merchant"),
    ("   ", "merchant"),
    ("!!!@@@", "merchant"),
])
def test_string_sanitization_parameterized(input_name, expected):
    """Test sanitize_short_name standardizes entity names and falls back to default on empty."""
    # Arrange & Act
    actual = sanitize_short_name(input_name)
    # Assert
    assert actual == expected


# ==============================================================================
# File Hashing & SHA-256 Tests
# ==============================================================================

def test_file_hashing_sha256():
    """Test calculate_file_hash computes valid 64-char SHA-256 checksum."""
    # Arrange
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"neutral dummy payload bytes for hashing verification 12345")
        tmp_path = tmp.name

    try:
        # Act
        file_hash = calculate_file_hash(tmp_path)
        # Assert
        assert isinstance(file_hash, str)
        assert len(file_hash) == 64
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ==============================================================================
# Logger Gateway & Audit Logging Tests
# ==============================================================================

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


def test_audit_log_service_and_dto():
    """Test ApiCallLogCreate DTO construction and AuditLogService method."""
    # Arrange
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

    # Act
    result = AuditLogService.log_api_call(dto)

    # Assert
    assert dto.provider == "test_provider"
    assert dto.input_tokens == 100
    assert result is True


# ==============================================================================
# PDF Service In-Memory / Adapter Tests
# ==============================================================================

def test_pdf_service_adapter():
    """Test PDFService adapter methods: fail-fast on missing file, and valid rendering on real PDF."""
    # Arrange
    service = PDFService()
    non_existent_file = "non_existent_dummy_file.pdf"

    # Act & Assert: Fail-Fast check on missing file
    with pytest.raises(FileNotFoundError):
        service.get_page_count(non_existent_file)

    with pytest.raises(FileNotFoundError):
        service.extract_text(non_existent_file)

    with pytest.raises(FileNotFoundError):
        service.render_page_to_pil(non_existent_file, 0)

    # Test with valid in-memory PDF
    import pymupdf as fitz
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_pdf_path = tmp.name

    try:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Hello PDF Unit Test")
        doc.save(tmp_pdf_path)
        doc.close()

        assert service.get_page_count(tmp_pdf_path) == 1
        text = service.extract_text(tmp_pdf_path)
        assert "Hello PDF Unit Test" in text

        pil_img = service.render_page_to_pil(tmp_pdf_path, 0, dpi=72)
        assert pil_img is not None
        assert pil_img.width > 0
    finally:
        if os.path.exists(tmp_pdf_path):
            os.remove(tmp_pdf_path)
