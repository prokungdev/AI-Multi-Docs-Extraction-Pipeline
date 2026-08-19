import os
import json
import unittest
import pymupdf as fitz
import pandas as pd

# Import modules to test
from src.core.pdf_splitter import split_pdf
from src.core.source_matcher import match_source
from src.core.transformer import transform_data
from src.core.initializer import initialize_storage_directories
from src.core.logger import setup_logger
from src.core.db import get_db_connection, initialize_db_schema, insert_relational_receipt

class TestPipeline(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Initialize logging and storage
        setup_logger("configs/settings.json")
        initialize_storage_directories("configs/settings.json")
        
        with open("configs/settings.json", "r", encoding="utf-8") as f:
            cls.settings = json.load(f)
        cls.domain = "expense_receipt"
        
        # 2. Create a mock PDF file using PyMuPDF
        cls.pdf_path = "test_spx_receipt.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # Insert text matching SPX Express rules
        text_content = (
            "SPX Express Tax Invoice / Receipt\n"
            "SPX Express (Thailand) Co., Ltd.\n"
            "Tax ID: 0105561164871\n"
            "Date: 2026-08-15\n"
            "Item: Shipping Service - SPXTH987654321, Qty: 1, Price: 120.00 THB\n"
            "Subtotal: 112.15 THB\n"
            "VAT (7%): 7.85 THB\n"
            "Net Total: 120.00 THB\n"
            "Paid via ShopeePay"
        )
        page.insert_text((50, 50), text_content)
        doc.save(cls.pdf_path)
        doc.close()
        print(f"\n[TEST SETUP] Generated mock PDF at: {cls.pdf_path}")
        
    @classmethod
    def tearDownClass(cls):
        # Clean up temporary test files
        if os.path.exists(cls.pdf_path):
            os.remove(cls.pdf_path)
            print(f"[TEST TEARDOWN] Cleaned up: {cls.pdf_path}")
            
    def test_01_pdf_splitting(self):
        """Test splitting PDF into optimized JPG image pages."""
        output_dir = "pipeline_storage/expense_receipt/02_split_pages"
        image_paths = split_pdf(self.pdf_path, output_dir, image_format="jpg")
        
        self.assertGreater(len(image_paths), 0)
        self.assertTrue(os.path.exists(image_paths[0]))
        self.assertTrue(image_paths[0].endswith(".jpg"))
        print(f"[TEST] PDF Splitting (JPG) test passed. Generated image: {image_paths[0]}")
        
    def test_01b_raw_image_processing(self):
        """Test processing raw image directly with resizing and JPG optimization."""
        from src.core.pdf_splitter import process_raw_image
        from PIL import Image
        
        # Create a test high-res image
        test_img_path = "temp_large_raw_receipt.png"
        img = Image.new("RGB", (2400, 3200), color=(255, 255, 255))
        img.save(test_img_path)
        
        output_dir = "pipeline_storage/expense_receipt/02_split_pages"
        out_jpg = process_raw_image(test_img_path, output_dir, image_format="jpg", max_dimension=1800, quality=85)
        
        self.assertTrue(os.path.exists(out_jpg))
        self.assertTrue(out_jpg.endswith(".jpg"))
        
        # Verify resized dimensions
        with Image.open(out_jpg) as proc_img:
            self.assertLessEqual(max(proc_img.size), 1800)
            
        if os.path.exists(test_img_path):
            os.remove(test_img_path)
        print(f"[TEST] Raw Image processing & resizing test passed. Output: {out_jpg}")

    def test_01c_filename_pattern_formatting(self):
        """Test formatting split page and archive filenames based on configurable patterns."""
        from src.core.pdf_splitter import format_page_filename
        
        # Test split pattern
        split_name = format_page_filename(
            pattern="{domain}_{source}_{original_filename}_{batch_id}_p{page_no}",
            domain="expense_receipt",
            source="spx_express",
            original_filename="SPXExpress_202606_000008.pdf",
            page_no=1,
            batch_id="452bdbcb-3099-4eb5-ab34-ac5eb60be8aa",
            image_format="jpg"
        )
        self.assertEqual(split_name, "expense_receipt_spx_express_SPXExpress_202606_000008_452bdbcb_p1.jpg")
        
        # Test archive pattern
        archive_name = format_page_filename(
            pattern="{domain}_{source}_{doc_no}_{batch_id}_p{page_no}",
            domain="expense_receipt",
            source="spx_express",
            doc_no="INV-20260815-001",
            page_no=1,
            batch_id="452bdbcb-3099-4eb5-ab34-ac5eb60be8aa",
            image_format="jpg"
        )
        self.assertEqual(archive_name, "expense_receipt_spx_express_INV-20260815-001_452bdbcb_p1.jpg")
        print(f"[TEST] Filename patterns test passed: Split='{split_name}', Archive='{archive_name}'")
        
    def test_02_source_matching(self):
        """Test matching source based on digital text rules."""
        # This should match 'spx_express' because of Tax ID '0105561164871'
        matched_source = match_source(self.pdf_path, self.domain)
        self.assertEqual(matched_source, "spx_express")
        print(f"[TEST] Source matching test passed. Matched: {matched_source}")
        
    def test_03_transformer_summary(self):
        """Test data transformer using the summary template (google_sheet_summary.json)."""
        mock_extracted = {
            "receipt_info": {
                "receipt_number": "INV-20260815-001",
                "transaction_date": "2026-08-15",
                "expense_category": "Delivery",
                "payment_method": "ShopeePay"
            },
            "merchant": {
                "name": "SPX Express (Thailand) Co., Ltd.",
                "tax_id": "0105561164871"
            },
            "items": [
                {"name": "Shipping Fee - SPXTH987654321", "qty": 1, "unit_price": 120.0, "total_price": 120.0}
            ],
            "totals": {
                "subtotal": 112.15,
                "discount": 0.0,
                "vat_amount": 7.85,
                "net_amount": 120.0
            }
        }
        
        template_path = "configs/domains/expense_receipt/outputs/google_sheet_summary.json"
        rows = transform_data(mock_extracted, template_path)
        
        # Verify output structure
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Transaction Date"], "2026-08-15")
        self.assertEqual(rows[0]["Merchant Name"], "SPX Express (Thailand) Co., Ltd.")
        self.assertEqual(rows[0]["Net Amount"], 120.0)
        self.assertEqual(rows[0]["Payment Method"], "ShopeePay")
        print("[TEST] Transformer (Summary) test passed.")
        
    def test_04_transformer_line_items(self):
        """Test data transformer using the line-items template (accounting_line_items.json)."""
        mock_extracted = {
            "receipt_info": {
                "receipt_number": "INV-20260815-001",
                "transaction_date": "2026-08-15",
                "expense_category": "Delivery",
                "payment_method": "ShopeePay"
            },
            "merchant": {
                "name": "SPX Express (Thailand) Co., Ltd.",
                "tax_id": "0105561164871"
            },
            "items": [
                {"name": "Shipping Fee - SPXTH987654321", "qty": 1, "unit_price": 100.0, "total_price": 100.0},
                {"name": "Packaging Material", "qty": 2, "unit_price": 10.0, "total_price": 20.0}
            ],
            "totals": {
                "subtotal": 120.0,
                "discount": 0.0,
                "vat_amount": 0.0,
                "net_amount": 120.0
            }
        }
        
        template_path = "configs/domains/expense_receipt/outputs/accounting_line_items.json"
        rows = transform_data(mock_extracted, template_path)
        
        # Verify output structure
        self.assertEqual(len(rows), 2)
        # Check first item row
        self.assertEqual(rows[0]["Item Name"], "Shipping Fee - SPXTH987654321")
        self.assertEqual(rows[0]["Quantity"], 1)
        self.assertEqual(rows[0]["Total Price"], 100.0)
        self.assertEqual(rows[0]["Net Amount"], 120.0)  # Cloned from top-level
        
        # Check second item row
        self.assertEqual(rows[1]["Item Name"], "Packaging Material")
        self.assertEqual(rows[1]["Quantity"], 2)
        self.assertEqual(rows[1]["Total Price"], 20.0)
        self.assertEqual(rows[1]["Net Amount"], 120.0)  # Cloned from top-level
        print("[TEST] Transformer (Line Items) test passed.")

    def test_05_relational_db_insert(self):
        """Test inserting extracted data into relational tables."""
        initialize_db_schema()
        
        mock_extracted = {
            "receipt_info": {
                "receipt_number": "INV-20260815-001",
                "transaction_date": "2026-08-15",
                "expense_category": "Delivery",
                "payment_method": "ShopeePay"
            },
            "merchant": {
                "name": "SPX Express (Thailand) Co., Ltd.",
                "tax_id": "0105561164871"
            },
            "items": [
                {"name": "Shipping Fee - SPXTH987654321", "qty": 1, "unit_price": 100.0, "total_price": 100.0},
                {"name": "Packaging Material", "qty": 2, "unit_price": 10.0, "total_price": 20.0}
            ],
            "totals": {
                "subtotal": 120.0,
                "discount": 0.0,
                "vat_amount": 0.0,
                "net_amount": 120.0
            }
        }
        
        doc_id = "test_doc_123"
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Ensure parent batch exists
        cursor.execute("INSERT OR REPLACE INTO processed_batches (batch_id, original_pdf_name, total_pages, storage_path, file_hash, created_at) VALUES ('test_batch_123', 'test.pdf', 1, 'path', 'hash123', '2026-08-15')")
        
        # Ensure dummy document exists
        cursor.execute("INSERT OR REPLACE INTO documents (document_id, batch_id, domain_id, source_id, status_code, created_at) VALUES ('test_doc_123', 'test_batch_123', 'expense_receipt', 'spx_express', 'PROCESSED', '2026-08-15')")
        conn.commit()
        
        success = insert_relational_receipt(doc_id, mock_extracted, "test.pdf", conn=conn)
        self.assertTrue(success)
        
        # Verify merchant was auto-created
        cursor.execute("SELECT * FROM merchant_master WHERE tax_id = '0105561164871'")
        merchant = cursor.fetchone()
        self.assertIsNotNone(merchant)
        self.assertEqual(merchant["merchant_name"], "SPX Express (Thailand) Co., Ltd.")
        
        # Verify receipt was created
        cursor.execute("SELECT * FROM expense_receipt WHERE document_id = 'test_doc_123'")
        receipt = cursor.fetchone()
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["net_amount"], 120.0)
        
        # Verify details were created
        cursor.execute("SELECT * FROM expense_receipt_d WHERE receipt_id = ?", (receipt["receipt_id"],))
        items = cursor.fetchall()
        self.assertEqual(len(items), 2)
        
        conn.close()
        print("[TEST] Relational database insertion test passed.")

if __name__ == "__main__":
    unittest.main()
