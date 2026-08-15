import os
import json
import unittest
import fitz  # PyMuPDF
import pandas as pd

# Import modules to test
from src.core.pdf_splitter import split_pdf
from src.core.source_matcher import match_source
from src.core.transformer import transform_data
from src.core.initializer import initialize_storage_directories
from src.core.logger import setup_logger

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
        """Test splitting PDF into image pages."""
        output_dir = "pipeline_storage/expense_receipt/02_split_pages"
        image_paths = split_pdf(self.pdf_path, output_dir)
        
        self.assertGreater(len(image_paths), 0)
        self.assertTrue(os.path.exists(image_paths[0]))
        self.assertTrue(image_paths[0].endswith(".png"))
        print(f"[TEST] PDF Splitting test passed. Generated image: {image_paths[0]}")
        
    def test_02_source_matching(self):
        """Test matching source based on digital text rules."""
        # This should match 'spx_express' because of Tax ID '0105561164871'
        matched_source = match_source(self.pdf_path, self.domain)
        self.assertEqual(matched_source, "spx_express")
        print(f"[TEST] Source matching test passed. Matched: {matched_source}")
        
    def test_03_transformer_summary(self):
        """Test data transformer using the summary template (google_sheet_summary.json)."""
        mock_extracted = {
            "transaction_date": "2026-08-15",
            "merchant_name": "SPX Express (Thailand) Co., Ltd.",
            "tax_id": "0105561164871",
            "expense_category": "Delivery",
            "items": [
                {"name": "Shipping Fee - SPXTH987654321", "qty": 1, "unit_price": 120.0, "total_price": 120.0}
            ],
            "financial_summary": {
                "subtotal": 112.15,
                "discount": 0.0,
                "vat_amount": 7.85,
                "net_amount": 120.0
            },
            "payment_method": "ShopeePay"
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
            "transaction_date": "2026-08-15",
            "merchant_name": "SPX Express (Thailand) Co., Ltd.",
            "tax_id": "0105561164871",
            "expense_category": "Delivery",
            "items": [
                {"name": "Shipping Fee - SPXTH987654321", "qty": 1, "unit_price": 100.0, "total_price": 100.0},
                {"name": "Packaging Material", "qty": 2, "unit_price": 10.0, "total_price": 20.0}
            ],
            "financial_summary": {
                "subtotal": 120.0,
                "discount": 0.0,
                "vat_amount": 0.0,
                "net_amount": 120.0
            },
            "payment_method": "ShopeePay"
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

if __name__ == "__main__":
    unittest.main()
