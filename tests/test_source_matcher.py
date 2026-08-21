import os
import unittest
import fitz

from src.core.config_loader import load_system_settings
from src.core.initializer import initialize_storage_directories
from src.core.logger import setup_logger
from src.core.source_matcher import match_source


class TestSourceMatcher(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        setup_logger("configs/settings.json")
        initialize_storage_directories("configs/settings.json")
        cls.settings = load_system_settings("configs/settings.json")
        cls.domain = "expense_receipt"

        # Generate mock PDF with generic mock merchant text
        cls.pdf_path = "mock_source_document.pdf"
        doc = fitz.open()
        page = doc.new_page()
        text_content = (
            "Mock Invoice Document Title\n"
            "SPX Express Tax Invoice / Receipt\n"
            "Tax ID: 0105561164871\n"
        )
        page.insert_text((50, 50), text_content)
        doc.save(cls.pdf_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.pdf_path):
            os.remove(cls.pdf_path)

    def test_source_matching(self):
        """Test rule-based merchant source matching using source matcher rules."""
        matched_source = match_source(self.pdf_path, domain=self.domain, settings=self.settings)
        self.assertIsNotNone(matched_source)
        self.assertIsInstance(matched_source, str)


if __name__ == "__main__":
    unittest.main()
