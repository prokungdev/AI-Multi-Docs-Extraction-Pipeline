"""
Integration tests for PDFService with real PDF rendering via PyMuPDF (fitz).
Enforces temporary isolated file generation and verifies post-test cleanup.
"""

import os
import tempfile
import pytest
import pymupdf as fitz
from src.infrastructure.pdf.pdf_service import PDFService


def test_pdf_service_adapter():
    """Test PDFService adapter methods: fail-fast on missing file, valid rendering, and cleanup."""
    # Arrange
    service = PDFService()
    non_existent_file = "non_existent_dummy_file.pdf"

    # 1. Fail-Fast check on missing file
    with pytest.raises(FileNotFoundError):
        service.get_page_count(non_existent_file)

    with pytest.raises(FileNotFoundError):
        service.extract_text(non_existent_file)

    with pytest.raises(FileNotFoundError):
        service.render_page_to_pil(non_existent_file, 0)

    # 2. Test with real PDF generated in isolated temp location
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_pdf_path = tmp.name

    try:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Hello PDF Integration Test")
        doc.save(tmp_pdf_path)
        doc.close()

        # Act & Assert
        assert service.get_page_count(tmp_pdf_path) == 1
        text = service.extract_text(tmp_pdf_path)
        assert "Hello PDF Integration Test" in text

        pil_img = service.render_page_to_pil(tmp_pdf_path, 0, dpi=72)
        assert pil_img is not None
        assert pil_img.width > 0
    finally:
        # Cleanup
        if os.path.exists(tmp_pdf_path):
            os.remove(tmp_pdf_path)

        # Cleanup Verification Step: Verify file is deleted
        assert not os.path.exists(tmp_pdf_path), f"Leakage detected: {tmp_pdf_path} was not deleted!"
