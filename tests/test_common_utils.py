"""Unit tests for shared common utilities, helpers, and pure functions."""

import os
import tempfile
import unittest

from src.domain.services.post_processor import normalize_date_to_ad
from src.infrastructure.common.utils import chunk_list
from src.infrastructure.persistence.documents import calculate_file_hash
from src.infrastructure.persistence.masters import sanitize_short_name


class TestDateNormalization(unittest.TestCase):
    """Test suite for normalize_date_to_ad."""

    def test_be_date_iso_format(self):
        """Tests YYYY-MM-DD format with BE year."""
        self.assertEqual(normalize_date_to_ad("2567-05-15"), "2024-05-15")
        self.assertEqual(normalize_date_to_ad("2568/12/31"), "2025-12-31")

    def test_be_date_dmy_format(self):
        """Tests DD/MM/YYYY and DD-MM-YYYY formats with BE year."""
        self.assertEqual(normalize_date_to_ad("15/05/2567"), "2024-05-15")
        self.assertEqual(normalize_date_to_ad("01-01-2566"), "2023-01-01")

    def test_ad_date_unchanged(self):
        """Tests Christian Era (AD) dates remain unchanged."""
        self.assertEqual(normalize_date_to_ad("2024-05-15"), "2024-05-15")
        self.assertEqual(normalize_date_to_ad("15/05/2024"), "2024-05-15")

    def test_boundary_years(self):
        """Tests boundary year conditions (> 2500)."""
        self.assertEqual(normalize_date_to_ad("2500-01-01"), "2500-01-01")
        self.assertEqual(normalize_date_to_ad("2501-01-01"), "1958-01-01")

    def test_empty_and_invalid_inputs(self):
        """Tests empty, whitespace, non-string, or non-matching inputs."""
        self.assertEqual(normalize_date_to_ad(""), "")
        self.assertEqual(normalize_date_to_ad(None), "")
        self.assertEqual(normalize_date_to_ad("   "), "")
        self.assertEqual(normalize_date_to_ad("invalid-date-string"), "invalid-date-string")


class TestListChunking(unittest.TestCase):
    """Test suite for chunk_list utility."""

    def test_chunk_even_distribution(self):
        """Tests dividing list evenly into equal sized sublists."""
        items = [1, 2, 3, 4, 5, 6]
        chunks = chunk_list(items, 2)
        self.assertEqual(chunks, [[1, 2], [3, 4], [5, 6]])

    def test_chunk_uneven_distribution(self):
        """Tests dividing list with leftover elements in last chunk."""
        items = ["a", "b", "c", "d", "e"]
        chunks = chunk_list(items, 2)
        self.assertEqual(chunks, [["a", "b"], ["c", "d"], ["e"]])

    def test_chunk_empty_list(self):
        """Tests chunking an empty list."""
        self.assertEqual(chunk_list([], 5), [])

    def test_chunk_invalid_size(self):
        """Tests chunking with size <= 0 returns list as single sublist."""
        items = [1, 2, 3]
        self.assertEqual(chunk_list(items, 0), [[1, 2, 3]])
        self.assertEqual(chunk_list(items, -1), [[1, 2, 3]])


class TestStringSanitization(unittest.TestCase):
    """Test suite for sanitize_short_name utility."""

    def test_sanitize_clean_name(self):
        """Tests already clean merchant name."""
        self.assertEqual(sanitize_short_name("7ELEVEN"), "7eleven")

    def test_sanitize_with_special_characters(self):
        """Tests replacing special characters and whitespace with underscores."""
        self.assertEqual(sanitize_short_name("Big C Supercenter"), "big_c_supercenter")
        self.assertEqual(sanitize_short_name("HomePro (HQ) #001"), "homepro_hq_001")

    def test_sanitize_empty_and_fallback(self):
        """Tests empty or whitespace input falls back to merchant."""
        self.assertEqual(sanitize_short_name(""), "merchant")
        self.assertEqual(sanitize_short_name("   "), "merchant")
        self.assertEqual(sanitize_short_name("!!!@@@"), "merchant")


class TestFileHashing(unittest.TestCase):
    """Test suite for calculate_file_hash utility."""

    def test_hash_calculation(self):
        """Tests SHA-256 binary hash computation of a file."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"neutral dummy payload bytes for hashing verification 12345")
            tmp_path = tmp.name

        try:
            file_hash = calculate_file_hash(tmp_path)
            self.assertIsInstance(file_hash, str)
            self.assertEqual(len(file_hash), 64)  # SHA-256 hex length
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class TestAppLogger(unittest.TestCase):
    """Test suite for AppLogger gateway and adapter."""

    def test_logger_methods_and_binding(self):
        """Tests that AppLogger gateway delegates standard logging levels without error."""
        from src.infrastructure.common.logger import logger, get_logger, AppLogger

        self.assertIsInstance(logger, AppLogger)
        # Verify standard methods execute without raising exceptions
        logger.debug("Test debug message")
        logger.info("Test info message")
        logger.warning("Test warning message")
        logger.error("Test error message")

        # Test binding context
        bound = logger.bind(custom_tag="unit_test")
        self.assertIsInstance(bound, AppLogger)
        bound.info("Test bound logger message")

        # Test get_logger with module name
        mod_logger = get_logger("test_module")
        self.assertIsInstance(mod_logger, AppLogger)


class TestAuditLogService(unittest.TestCase):
    """Test suite for AuditLogService and ApiCallLogCreate DTO."""

    def test_log_dto_validation_and_service(self):
        """Tests ApiCallLogCreate DTO construction and AuditLogService method."""
        from src.infrastructure.persistence.logs import ApiCallLogCreate, AuditLogService
        import uuid

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
        self.assertEqual(dto.provider, "test_provider")
        self.assertEqual(dto.input_tokens, 100)

        # Test service method
        result = AuditLogService.log_api_call(dto)
        self.assertTrue(result)


class TestPDFService(unittest.TestCase):
    """Test suite for PDFService adapter and facade."""

    def setUp(self):
        """Creates a dummy PDF file for testing."""
        import pymupdf as fitz
        self.tmp_dir = tempfile.mkdtemp()
        self.pdf_path = os.path.join(self.tmp_dir, "test_sample.pdf").replace("\\", "/")
        doc = fitz.open()
        page = doc.new_page(width=300, height=300)
        page.insert_text((50, 50), "Sample PDF Document for PDFService Unit Tests")
        doc.save(self.pdf_path)
        doc.close()

    def tearDown(self):
        """Cleans up temporary test files."""
        if os.path.exists(self.pdf_path):
            os.remove(self.pdf_path)
        if os.path.exists(self.tmp_dir):
            import shutil
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_get_page_count(self):
        """Tests page count retrieval via PDFService."""
        from src.infrastructure.pdf.pdf_service import PDFService
        count = PDFService.get_page_count(self.pdf_path)
        self.assertEqual(count, 1)

    def test_extract_text(self):
        """Tests digital text extraction via PDFService."""
        from src.infrastructure.pdf.pdf_service import PDFService
        text = PDFService.extract_text(self.pdf_path)
        self.assertIn("Sample PDF Document", text)

    def test_render_page_to_pil(self):
        """Tests rendering page to PIL Image via PDFService."""
        from src.infrastructure.pdf.pdf_service import PDFService
        pil_img = PDFService.render_page_to_pil(self.pdf_path, page_index=0, dpi=100)
        self.assertIsNotNone(pil_img)
        self.assertGreater(pil_img.width, 0)
        self.assertGreater(pil_img.height, 0)


if __name__ == "__main__":
    unittest.main()
