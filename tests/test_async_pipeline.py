import os
import unittest
import asyncio
import pymupdf as fitz
from src.core.pdf_splitter import async_split_pdf, async_process_raw_image
from src.core.pipeline import async_run_extract

class TestAsyncPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pdf_path = "test_async_mock.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Async Pipeline Test PDF Content")
        doc.save(cls.pdf_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.pdf_path):
            os.remove(cls.pdf_path)

    def test_01_async_split_pdf(self):
        """Test asynchronous PDF splitting."""
        output_dir = "pipeline_storage/expense_receipt/02_split_pages"
        image_paths = asyncio.run(async_split_pdf(self.pdf_path, output_dir, image_format="jpg"))

        self.assertGreater(len(image_paths), 0)
        self.assertTrue(os.path.exists(image_paths[0]))
        print(f"[TEST] Async PDF Splitting test passed. Image: {image_paths[0]}")

    def test_02_async_process_raw_image(self):
        """Test asynchronous raw image processing."""
        from PIL import Image
        test_img = "test_async_raw.png"
        img = Image.new("RGB", (1000, 1000), color=(200, 200, 200))
        img.save(test_img)

        output_dir = "pipeline_storage/expense_receipt/02_split_pages"
        out_jpg = asyncio.run(async_process_raw_image(test_img, output_dir, image_format="jpg"))

        self.assertTrue(os.path.exists(out_jpg))
        if os.path.exists(test_img):
            os.remove(test_img)
        print(f"[TEST] Async Raw Image Processing test passed. Output: {out_jpg}")

    def test_03_async_run_extract_empty_queue(self):
        """Test async_run_extract when queue is empty."""
        res = asyncio.run(async_run_extract(domain="expense_receipt"))
        self.assertTrue(res["success"])
        print(f"[TEST] Async Extract empty queue test passed: {res}")

if __name__ == "__main__":
    unittest.main()
