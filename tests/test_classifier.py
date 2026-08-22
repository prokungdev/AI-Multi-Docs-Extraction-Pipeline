import os
import unittest
import pymupdf

from src.core.classifier import classify_drop_zone_document, sanitize_short_name, fast_filename_prefix_match
from src.core.db import (
    initialize_db_schema,
    seed_initial_data,
    get_merchant_by_tax_id,
    approve_merchant,
    ignore_merchant,
    get_pending_merchants,
    check_short_name_duplicate,
    check_file_prefix_duplicate
)
from src.core.pipeline.split_stage import release_pending_merchant_files


class TestClassifierAndGatekeeper(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db_path = "storage/test_classifier.db"
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
        initialize_db_schema()
        seed_initial_data()

        # Create mock PDF with Thai tax ID
        cls.pdf_path = "test_classifier_sample.pdf"
        doc = pymupdf.open()
        p = doc.new_page()
        p.insert_text(
            (50, 50),
            "บริษัท ซีพี ออลล์ จำกัด (มหาชน)\n"
            "Tax ID: 0107542000011\n"
            "Date: 2026-08-22\n"
            "Item: Coffee 1x 50.00 THB\n"
            "Total: 50.00 THB\n"
        )
        doc.save(cls.pdf_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        from src.core.db.connection import get_engine
        try:
            get_engine().dispose()
        except Exception:
            pass
        for f in [cls.pdf_path, cls.db_path]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        os.environ.pop("DB_PATH_OVERRIDE", None)

    def test_01_sanitize_short_name(self):
        """Test short_name sanitization rules."""
        self.assertEqual(sanitize_short_name("บริษัท ซีพี ออลล์ จำกัด (มหาชน)"), "merchant")
        self.assertEqual(sanitize_short_name("PTT Oil and Retail Business Public Co., Ltd."), "ptt_oil_and_retail_business_public")
        self.assertEqual(sanitize_short_name("Starbucks Coffee (Thailand)"), "starbucks_coffee_thailand")
        self.assertEqual(sanitize_short_name(""), "merchant")

    def test_02_new_merchant_auto_discovery_and_hold(self):
        """Test auto-discovery of new merchant and HOLD pipeline action."""
        cls_res = classify_drop_zone_document(self.pdf_path, domain="expense_receipt")
        self.assertEqual(cls_res["tax_id"], "0107542000011")
        self.assertEqual(cls_res["pipeline_action"], "HOLD")
        self.assertEqual(cls_res["merchant_status"], "PENDING")

        # Verify in DB
        merchant = get_merchant_by_tax_id("0107542000011")
        self.assertIsNotNone(merchant)
        self.assertEqual(merchant["status_code"], "PENDING")

        # Verify pending list
        pending = get_pending_merchants()
        self.assertGreaterEqual(len(pending), 1)
        self.assertIn("0107542000011", [m["tax_id"] for m in pending])

    def test_03_merchant_approval_flow(self):
        """Test approving merchant and subsequent classification PROCEED."""
        merchant = get_merchant_by_tax_id("0107542000011")
        self.assertIsNotNone(merchant)

        # Approve merchant with custom short_name and file_prefix
        ok, msg = approve_merchant(
            merchant["merchant_id"],
            approved_by="test_admin",
            short_name="cp_all_th",
            file_prefix="cp_all"
        )
        self.assertTrue(ok)

        # Classify again -> should PROCEED
        cls_res = classify_drop_zone_document(self.pdf_path, domain="expense_receipt")
        self.assertEqual(cls_res["pipeline_action"], "PROCEED")
        self.assertEqual(cls_res["merchant_status"], "APPROVED")

    def test_04_zero_cost_file_prefix_matching(self):
        """Test zero-cost fast bypass match based on file_prefix."""
        # When filename starts with approved file_prefix 'cp_all'
        bypass_match = fast_filename_prefix_match("storage/expense_receipt/01_drop_zone/Upload/cp_all_inv202608.pdf")
        self.assertIsNotNone(bypass_match)
        self.assertTrue(bypass_match["zero_cost_bypass"])
        self.assertEqual(bypass_match["pipeline_action"], "PROCEED")
        self.assertEqual(bypass_match["short_name"], "cp_all_th")

        # Non-matching filename should return None for AI fallback
        non_match = fast_filename_prefix_match("storage/expense_receipt/01_drop_zone/Upload/unknown_scan_001.pdf")
        self.assertIsNone(non_match)

    def test_05_unique_validation(self):
        """Test duplicate validation for short_name and file_prefix."""
        # 'cp_all_th' and 'cp_all' exist now
        self.assertTrue(check_short_name_duplicate("cp_all_th"))
        self.assertTrue(check_file_prefix_duplicate("cp_all"))
        self.assertFalse(check_short_name_duplicate("ptt_retail"))
        self.assertFalse(check_file_prefix_duplicate("ptt_retail"))

    def test_06_merchant_ignored_flow(self):
        """Test ignoring merchant and subsequent IGNORE routing."""
        merchant = get_merchant_by_tax_id("0107542000011")
        ok, msg = ignore_merchant(merchant["merchant_id"], approved_by="test_admin")
        self.assertTrue(ok)

        # Classify again -> should IGNORE
        cls_res = classify_drop_zone_document(self.pdf_path, domain="expense_receipt")
        self.assertEqual(cls_res["pipeline_action"], "IGNORE")
        self.assertEqual(cls_res["merchant_status"], "IGNORED")


if __name__ == "__main__":
    unittest.main()
