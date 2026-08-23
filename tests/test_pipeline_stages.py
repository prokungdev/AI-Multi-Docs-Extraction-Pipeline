import os
import unittest
import pymupdf as fitz
from PIL import Image

from src.core.config_loader import load_system_settings
from src.core.initializer import initialize_storage_directories
from src.core.logger import setup_logger
from src.core.pdf_splitter import split_pdf, process_raw_image, format_page_filename
from src.core.classifier import classify_drop_zone_document, sanitize_short_name, fast_filename_prefix_match
from src.core.source_matcher import match_source
from src.core.pipeline.stage_1_ingestion import release_pending_merchant_files
from src.core.db import (
    initialize_db_schema,
    seed_initial_data,
    get_merchant_by_tax_id,
    approve_merchant,
    ignore_merchant,
    get_pending_merchants,
    check_short_name_duplicate,
    check_file_prefix_duplicate,
)


class TestPdfSplitter(unittest.TestCase):
    """
    Test suite for PDF splitting, image resizing, and filename pattern formatting.
    """

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
        import shutil
        if os.path.exists(cls.pdf_path):
            os.remove(cls.pdf_path)
        mock_dir = f"storage/{cls.mock_domain}"
        if os.path.exists(mock_dir):
            shutil.rmtree(mock_dir, ignore_errors=True)

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
        """Test split and archive filename pattern generation with {tax_id} and fallback."""
        # 1. Pattern with tax_id provided
        split_name_tax = format_page_filename(
            pattern="{doc_type}_{tax_id}_{original_filename}_{batch_id}_p{page_no}",
            doc_type=self.mock_domain,
            tax_id="0107542000011",
            original_filename="mock_invoice_001.pdf",
            page_no=1,
            batch_id="452bdbcb",
            image_format="jpg",
        )
        self.assertEqual(
            split_name_tax, "mock_domain_0107542000011_mock_invoice_001_452bdbcb_p1.jpg"
        )

        # 2. Pattern with missing tax_id (defaults to no_tax)
        split_name_notax = format_page_filename(
            pattern="{doc_type}_{tax_id}_{original_filename}_{batch_id}_p{page_no}",
            doc_type=self.mock_domain,
            tax_id="",
            original_filename="mock_invoice_001.pdf",
            page_no=1,
            batch_id="452bdbcb",
            image_format="jpg",
        )
        self.assertEqual(
            split_name_notax, "mock_domain_no_tax_mock_invoice_001_452bdbcb_p1.jpg"
        )

        # 3. Backward compatible pattern with {domain} and {source}
        split_name_legacy = format_page_filename(
            pattern="{domain}_{source}_{original_filename}_{batch_id}_p{page_no}",
            domain=self.mock_domain,
            source=self.mock_source,
            original_filename="mock_invoice_001.pdf",
            page_no=1,
            batch_id="452bdbcb",
            image_format="jpg",
        )
        self.assertEqual(
            split_name_legacy, "mock_domain_mock_source_mock_invoice_001_452bdbcb_p1.jpg"
        )


class TestClassifierAndGatekeeper(unittest.TestCase):
    """
    Test suite for Drop Zone classification, OCR/Vision Gatekeeper, and Merchant routing.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile, uuid
        cls.db_path = os.path.join(tempfile.gettempdir(), f"test_classifier_{uuid.uuid4().hex[:8]}.db").replace("\\", "/")
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path
        initialize_db_schema()
        seed_initial_data()

        # Create mock PDF with Thai tax ID
        cls.pdf_path = "test_classifier_sample.pdf"
        doc = fitz.open()
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
        import gc
        from src.core.db.connection import get_engine
        try:
            get_engine().dispose()
        except Exception:
            pass
        gc.collect()
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
        cls_res = classify_drop_zone_document(self.pdf_path, doc_type="expense_receipt")
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
        cls_res = classify_drop_zone_document(self.pdf_path, doc_type="expense_receipt")
        self.assertEqual(cls_res["pipeline_action"], "PROCEED")
        self.assertEqual(cls_res["merchant_status"], "APPROVED")

    def test_04_zero_cost_file_prefix_matching(self):
        """Test zero-cost fast bypass match based on file_prefix."""
        # When filename starts with approved file_prefix 'cp_all'
        bypass_match = fast_filename_prefix_match("storage/companies/C00000_SAMPLE/expense_receipt/01_drop_zone/Upload/cp_all_inv202608.pdf")
        self.assertIsNotNone(bypass_match)
        self.assertTrue(bypass_match["zero_cost_bypass"])
        self.assertEqual(bypass_match["pipeline_action"], "PROCEED")
        self.assertEqual(bypass_match["short_name"], "cp_all_th")

        # Non-matching filename should return None for AI fallback
        non_match = fast_filename_prefix_match("storage/companies/C00000_SAMPLE/expense_receipt/01_drop_zone/Upload/unknown_scan_001.pdf")
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
        cls_res = classify_drop_zone_document(self.pdf_path, doc_type="expense_receipt")
        self.assertEqual(cls_res["pipeline_action"], "IGNORE")
        self.assertEqual(cls_res["merchant_status"], "IGNORED")


class TestSourceMatcher(unittest.TestCase):
    """
    Test suite for merchant source matching against domain rule definitions.
    """

    @classmethod
    def setUpClass(cls):
        setup_logger("configs/settings.json")
        initialize_storage_directories("configs/settings.json")
        cls.settings = load_system_settings("configs/settings.json")
        cls.doc_type = "expense_receipt"

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
        matched_source = match_source(self.pdf_path, doc_type=self.doc_type, settings=self.settings)
        self.assertIsNotNone(matched_source)
        self.assertIsInstance(matched_source, str)


if __name__ == "__main__":
    unittest.main()
