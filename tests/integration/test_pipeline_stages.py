import os
import unittest
import pymupdf as fitz
from PIL import Image

from src.infrastructure.common.config_loader import load_system_settings
from src.application.usecases.initializer import initialize_storage_directories
from src.infrastructure.common.logger import setup_logger
from src.infrastructure.pdf.image_service import split_pdf, process_raw_image, format_page_filename
from src.domain.services.classifier import sanitize_short_name
from src.application.usecases.classifier import (
    classify_drop_zone_document,
    classify_document,
    fast_filename_prefix_match,
)
from src.application.pipeline.stage_1_ingestion import release_pending_merchant_files
from src.infrastructure.persistence import (
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
        import tempfile
        setup_logger("configs/settings.json")
        cls.settings = load_system_settings("configs/settings.json")
        cls.temp_dir = tempfile.mkdtemp()
        cls.mock_domain = "mock_domain"
        cls.mock_source = "mock_source"

        # Generate mock PDF for testing inside isolated temp directory
        cls.pdf_path = os.path.join(cls.temp_dir, "mock_document.pdf").replace("\\", "/")
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
        if hasattr(cls, "temp_dir") and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_pdf_splitting(self):
        """Test splitting PDF into JPG page images using isolated temp paths."""
        output_dir = os.path.join(self.temp_dir, "03_preprocess").replace("\\", "/")
        os.makedirs(output_dir, exist_ok=True)
        image_paths = split_pdf(self.pdf_path, output_dir, image_format="jpg")

        self.assertGreater(len(image_paths), 0)
        for img in image_paths:
            self.assertTrue(os.path.exists(img))
            self.assertTrue(img.endswith(".jpg"))

    def test_raw_image_processing(self):
        """Test processing & resizing raw image files in isolated temp paths."""
        output_dir = os.path.join(self.temp_dir, "03_preprocess").replace("\\", "/")
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

        # 3. Pattern with {doc_type} and {source}
        split_name_custom = format_page_filename(
            pattern="{doc_type}_{source}_{original_filename}_{batch_id}_p{page_no}",
            doc_type=self.mock_domain,
            source=self.mock_source,
            original_filename="mock_invoice_001.pdf",
            page_no=1,
            batch_id="452bdbcb",
            image_format="jpg",
        )
        self.assertEqual(
            split_name_custom, "mock_domain_mock_source_mock_invoice_001_452bdbcb_p1.jpg"
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
        from src.infrastructure.persistence.connection import get_engine
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
        """Test auto-discovery of new merchant and HOLD pipeline action via AI classification."""
        from unittest.mock import patch
        from src.infrastructure.ai.ai_service import ai_service

        mock_payload = {
            "tax_id": "0107542000011",
            "merchant_name": "CP All",
            "suggested_short_name": "cp_all"
        }
        with patch.object(ai_service, "api_key", "test_key"), \
             patch.object(ai_service, "extract_structured_json", return_value=(mock_payload, {})):
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
        from unittest.mock import patch
        from src.infrastructure.ai.ai_service import ai_service

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
        mock_payload = {
            "tax_id": "0107542000011",
            "merchant_name": "CP All",
            "suggested_short_name": "cp_all"
        }
        with patch.object(ai_service, "api_key", "test_key"), \
             patch.object(ai_service, "extract_structured_json", return_value=(mock_payload, {})):
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
        from unittest.mock import patch
        from src.infrastructure.ai.ai_service import ai_service

        merchant = get_merchant_by_tax_id("0107542000011")
        ok, msg = ignore_merchant(merchant["merchant_id"], approved_by="test_admin")
        self.assertTrue(ok)

        # Classify again -> should IGNORE
        mock_payload = {
            "tax_id": "0107542000011",
            "merchant_name": "CP All",
            "suggested_short_name": "cp_all"
        }
        with patch.object(ai_service, "api_key", "test_key"), \
             patch.object(ai_service, "extract_structured_json", return_value=(mock_payload, {})):
            cls_res = classify_drop_zone_document(self.pdf_path, doc_type="expense_receipt")
            self.assertEqual(cls_res["pipeline_action"], "IGNORE")
            self.assertEqual(cls_res["merchant_status"], "IGNORED")


class TestUnifiedSourceClassifier(unittest.TestCase):
    """
    Test suite for merchant source classification using unified classifier engine.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile, uuid
        setup_logger("configs/settings.json")
        cls.settings = load_system_settings("configs/settings.json")
        cls.doc_type = "expense_receipt"
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(tempfile.gettempdir(), f"test_unified_{uuid.uuid4().hex[:8]}.db").replace("\\", "/")
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path
        initialize_db_schema()
        seed_initial_data()

        # Generate mock PDF with generic mock merchant text in isolated temp directory
        cls.pdf_path = os.path.join(cls.temp_dir, "mock_source_document.pdf").replace("\\", "/")
        doc = fitz.open()
        page = doc.new_page()
        text_content = (
            "SPX Express Tax Invoice / Receipt\n"
            "Tax ID: 0105561164871\n"
            "Item: Shipping Fee, Qty: 1, Price: 45.00 THB\n"
        )
        page.insert_text((50, 50), text_content)
        doc.save(cls.pdf_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        import shutil, gc
        from src.infrastructure.persistence.connection import dispose_all_engines
        dispose_all_engines()
        gc.collect()
        if hasattr(cls, "temp_dir") and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
        if hasattr(cls, "db_path") and os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
        os.environ.pop("DB_PATH_OVERRIDE", None)

    def test_classify_document_pipeline(self):
        """Test unified document classification routing with AI fallback or safe quarantine."""
        cls_res = classify_document(self.pdf_path, doc_type=self.doc_type)
        self.assertIn("folder_identifier", cls_res)
        self.assertIn("pipeline_action", cls_res)


class TestSmartChunkCheckpointAndResume(unittest.TestCase):
    """
    Test suite for Smart Chunk-Level Checkpointing, Partial Failure Tracking, and Resuming.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile, uuid
        setup_logger("configs/settings.json")
        cls.settings = load_system_settings("configs/settings.json")
        cls.doc_type = "expense_receipt"
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(tempfile.gettempdir(), f"test_chunking_{uuid.uuid4().hex[:8]}.db").replace("\\", "/")
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path
        initialize_db_schema()
        seed_initial_data()

        # Create a 5-page mock PDF with approved cash_slip prefix
        cls.pdf_path = os.path.join(cls.temp_dir, "cash_slip_multi_page.pdf").replace("\\", "/")
        doc = fitz.open()
        for page_idx in range(1, 6):
            page = doc.new_page()
            page.insert_text((50, 50), f"Mock Cash Slip - Page {page_idx}\nTax ID: 0000000000000\nTotal: 500.00 THB")
        doc.save(cls.pdf_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        import shutil, gc
        from src.infrastructure.persistence.connection import dispose_all_engines
        dispose_all_engines()
        gc.collect()
        if hasattr(cls, "temp_dir") and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
        if hasattr(cls, "db_path") and os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
        os.environ.pop("DB_PATH_OVERRIDE", None)

    def test_01_multi_page_splitting_and_chunk_assignment(self):
        """Test that PDF splitting correctly computes and records chunk_index per page in DB."""
        from unittest.mock import patch
        from src.application.pipeline.stage_1_ingestion import split_and_match
        from src.infrastructure.persistence import get_batch_pages

        # Mock max_images_per_request to 2 pages per chunk
        with patch("src.application.pipeline.stage_1_ingestion.get_ai_provider_config", return_value={"max_images_per_request": 2}):
            results = split_and_match(input_file=self.pdf_path, doc_type="expense_receipt")
            self.assertEqual(len(results), 1)
            batch_id = results[0]["batch_id"]
            self.assertEqual(results[0]["total_pages"], 5)

            pages = get_batch_pages(batch_id)
            self.assertEqual(len(pages), 5)
            
            # Page 1, 2 -> chunk 1
            self.assertEqual(pages[0]["chunk_index"], 1)
            self.assertEqual(pages[1]["chunk_index"], 1)
            # Page 3, 4 -> chunk 2
            self.assertEqual(pages[2]["chunk_index"], 2)
            self.assertEqual(pages[3]["chunk_index"], 2)
            # Page 5 -> chunk 3
            self.assertEqual(pages[4]["chunk_index"], 3)
            self.__class__.batch_id = batch_id

    def test_02_chunk_partial_failure_and_smart_resume(self):
        """Test partial failure at chunk 2, checkpointing of chunk 1, and subsequent resume."""
        from unittest.mock import patch
        from src.application.pipeline.stage_2_extraction import extract_documents
        from src.infrastructure.persistence import get_batch_pages, get_unextracted_chunks_for_batch

        batch_id = getattr(self.__class__, "batch_id", None)
        self.assertIsNotNone(batch_id)

        # 1. First run: Chunk 1 succeeds, Chunk 2 raises AI RateLimitError
        def mock_extract_document_data(**kwargs):
            chunk_index = kwargs.get("chunk_index", 1)
            if chunk_index == 1:
                return {"documents": [{"doc_number": "INV-001", "total_amount": 100.0}]}
            elif chunk_index == 2:
                raise RuntimeError("AI RateLimit 429: Resource exhausted")
            return {"documents": [{"doc_number": "INV-003", "total_amount": 300.0}]}

        with patch("src.application.pipeline.stage_2_extraction.extract_document_data", side_effect=mock_extract_document_data):
            res = extract_documents(doc_type="expense_receipt")
            # Should have processed 0 completed batches because chunk 2 failed
            self.assertEqual(res["batches_processed"], 0)

        # Check DB state
        pages = get_batch_pages(batch_id)
        # Chunk 1 (pages 1-2) -> EXTRACTED
        self.assertEqual(pages[0]["status_code"], "EXTRACTED")
        self.assertEqual(pages[1]["status_code"], "EXTRACTED")
        # Chunk 2 (pages 3-4) -> FAILED
        self.assertEqual(pages[2]["status_code"], "FAILED")
        self.assertIn("RateLimit", pages[2]["error_reason"])
        self.assertEqual(pages[3]["status_code"], "FAILED")
        
        # Pending unextracted chunks must be [2, 3]
        unextracted = get_unextracted_chunks_for_batch(batch_id)
        self.assertEqual(unextracted, [2, 3])

        # 2. Second run (Resume): All chunks succeed
        call_counts = {"chunk_1": 0, "chunk_2": 0, "chunk_3": 0}

        def mock_resume_extract(**kwargs):
            chunk_idx = kwargs.get("chunk_index", 1)
            if chunk_idx == 1:
                call_counts["chunk_1"] += 1
                return {"documents": [{"doc_number": "INV-001", "total_amount": 100.0}]}
            elif chunk_idx == 2:
                call_counts["chunk_2"] += 1
                return {"documents": [{"doc_number": "INV-002", "total_amount": 200.0}]}
            elif chunk_idx == 3:
                call_counts["chunk_3"] += 1
                return {"documents": [{"doc_number": "INV-003", "total_amount": 300.0}]}

        with patch("src.application.pipeline.stage_2_extraction.extract_document_data", side_effect=mock_resume_extract):
            res = extract_documents(doc_type="expense_receipt")
            self.assertEqual(res["batches_processed"], 1)

        # Chunk 1 was loaded from cache and NOT re-called!
        self.assertEqual(call_counts["chunk_1"], 0)
        # Chunk 2 and Chunk 3 were called and processed!
        self.assertEqual(call_counts["chunk_2"], 1)
        self.assertEqual(call_counts["chunk_3"], 1)

        # Verify all pages in DB are now EXTRACTED
        final_pages = get_batch_pages(batch_id)
        for p in final_pages:
            self.assertEqual(p["status_code"], "EXTRACTED")

        # Unextracted chunks should now be empty
        self.assertEqual(get_unextracted_chunks_for_batch(batch_id), [])


if __name__ == "__main__":
    unittest.main()
