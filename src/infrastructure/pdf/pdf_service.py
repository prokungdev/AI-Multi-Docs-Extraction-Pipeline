"""
PDF Processing Service Layer (Adapter & Facade Pattern).
Encapsulates PDF parsing, text extraction, and page rendering engines.
Isolates third-party PDF dependencies (e.g. PyMuPDF) from business logic.
"""

import os
from typing import Optional, List, Generator
from contextlib import contextmanager
from PIL import Image
import pymupdf as fitz
from src.core.logger import logger


class PDFService:
    """
    Standardized PDF Engine Gateway.
    Provides clean high-level abstractions for PDF document manipulation.
    """

    @staticmethod
    @contextmanager
    def open_pdf(pdf_path: str) -> Generator[fitz.Document, None, None]:
        """
        Context manager ensuring safe document lifecycle and immediate file handle release.
        Prevents file lock issues on Windows OS.
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found at: {pdf_path}")
        doc = fitz.open(pdf_path)
        try:
            yield doc
        finally:
            doc.close()

    @classmethod
    def get_page_count(cls, pdf_path: str) -> int:
        """
        Returns total page count of a PDF file.
        """
        with cls.open_pdf(pdf_path) as doc:
            return len(doc)

    @classmethod
    def extract_text(cls, pdf_path: str, max_pages: Optional[int] = None) -> str:
        """
        Extracts digital plain text content across all or limited pages of a PDF.
        """
        extracted_text = ""
        with cls.open_pdf(pdf_path) as doc:
            total_pages = len(doc)
            pages_to_read = min(total_pages, max_pages) if max_pages else total_pages
            for page_num in range(pages_to_read):
                page = doc.load_page(page_num)
                extracted_text += page.get_text() or ""
        return extracted_text

    @classmethod
    def render_page_to_pil(cls, pdf_path: str, page_index: int = 0, dpi: int = 150) -> Image.Image:
        """
        Renders a single PDF page (0-indexed) into a Pillow Image object.
        """
        with cls.open_pdf(pdf_path) as doc:
            if page_index < 0 or page_index >= len(doc):
                raise IndexError(f"Page index {page_index} out of range (Total: {len(doc)})")
            page = doc.load_page(page_index)
            pix = page.get_pixmap(dpi=dpi)
            mode = "RGBA" if pix.alpha else "RGB"
            return Image.frombytes(mode, [pix.width, pix.height], pix.samples)

    @classmethod
    def extract_page_to_pdf(cls, pdf_path: str, page_num: int, output_path: str) -> None:
        """
        Extracts a single page (1-indexed) from a PDF and saves as a standalone single-page PDF.
        """
        with cls.open_pdf(pdf_path) as doc:
            idx = page_num - 1
            if idx < 0 or idx >= len(doc):
                raise IndexError(f"Page number {page_num} out of range for PDF with {len(doc)} pages.")
            new_doc = fitz.open()
            try:
                new_doc.insert_pdf(doc, from_page=idx, to_page=idx)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                new_doc.save(output_path)
                logger.info(f"Extracted page {page_num} to '{output_path}'")
            finally:
                new_doc.close()
