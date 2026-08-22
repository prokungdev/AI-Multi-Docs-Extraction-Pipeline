import os
import unittest
import fitz
from PIL import Image

from src.core.config_loader import load_system_settings
from src.core.initializer import initialize_storage_directories
from src.core.logger import setup_logger
from src.core.pdf_splitter import split_pdf, process_raw_image, format_page_filename


class TestPdfSplitter(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        setup_logger("configs/settings.json")
        initialize_storage_directories("configs/settings.json")
        cls.settings = load_system_settings("configs/settings.json")
        cls.mock_domain = "mock_domain"
        cls.mock_source = "mock_source"

        # Generate mock PDF for testing
        cls.pdf_path = "mock_document.pdf"
        doc = fitz.open()
        page = doc.new_page()
        text_content = (
            "Mock Invoice Document Title\n"
            "Mock Business Entity Ltd.\n"
            "Tax ID: 9999999999999\n"
            "Date: 2026-01-01\n"
            "Item: Mock Product A, Qty: 1, Price: 100.00 THB\n"
        )
        page.insert_text((50, 50), text_content)
        doc.save(cls.pdf_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.pdf_path):
            os.remove(cls.pdf_path)

    def test_pdf_splitting(self):
        """Test splitting PDF into JPG page images using mock paths."""
        output_dir = f"storage/{self.mock_domain}/03_preprocess"
        os.makedirs(output_dir, exist_ok=True)
        image_paths = split_pdf(self.pdf_path, output_dir, image_format="jpg")

        self.assertGreater(len(image_paths), 0)
        for img in image_paths:
            self.assertTrue(os.path.exists(img))
            self.assertTrue(img.endswith(".jpg"))

    def test_raw_image_processing(self):
        """Test processing & resizing raw image files."""
        output_dir = f"storage/{self.mock_domain}/03_preprocess"
        os.makedirs(output_dir, exist_ok=True)
        temp_img_path = os.path.join(output_dir, "temp_large_raw_mock.png").replace("\\", "/")

        img = Image.new("RGB", (3000, 4000), color="white")
        img.save(temp_img_path)

        out_name = "temp_temp_large_raw_mock_page_1.jpg"
        final_path = process_raw_image(temp_img_path, output_dir, out_name, max_dimension=1920)

        self.assertTrue(os.path.exists(final_path))

        with Image.open(final_path) as resized_img:
            self.assertLessEqual(max(resized_img.size), 1920)

        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)

    def test_filename_patterns(self):
        """Test split and archive filename pattern generation with mock identifiers."""
        split_name = format_page_filename(
            pattern="{domain}_{source}_{original_filename}_{batch_id}_p{page_no}",
            domain=self.mock_domain,
            source=self.mock_source,
            original_filename="mock_invoice_001.pdf",
            page_no=1,
            batch_id="452bdbcb",
            image_format="jpg",
        )
        self.assertEqual(
            split_name, "mock_domain_mock_source_mock_invoice_001_452bdbcb_p1.jpg"
        )



if __name__ == "__main__":
    unittest.main()
