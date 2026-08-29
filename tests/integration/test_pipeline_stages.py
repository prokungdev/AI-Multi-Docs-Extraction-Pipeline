import os
import json
import unittest
import pymupdf as fitz
from PIL import Image

from src.infrastructure.core.config import load_system_settings
from src.application.usecases.initializer import initialize_storage_directories
from src.infrastructure.core.logger import setup_logger
from src.infrastructure.external.pdf.image_service import split_pdf, process_raw_image, format_page_filename
from src.domain.services.text_normalizer import sanitize_short_name
from src.application.usecases.classifier import (
    classify_drop_zone_document,
    classify_document,
    fast_filename_prefix_match,
)
from src.application.pipeline.stage_1_ingestion import release_pending_merchant_files
from src.infrastructure.database import (
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
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(tempfile.gettempdir(), f"test_classifier_{uuid.uuid4().hex[:8]}.db").replace("\\", "/")
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path
        os.environ["STORAGE_ROOT_OVERRIDE"] = cls.temp_dir
        initialize_db_schema()
        seed_initial_data()

        # Create mock PDF with Thai tax ID inside isolated temp dir
        cls.pdf_path = os.path.join(cls.temp_dir, "test_classifier_sample.pdf").replace("\\", "/")
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
        import gc, shutil
        from src.infrastructure.database.engine import get_engine
        try:
            get_engine().dispose()
        except Exception:
            pass
        gc.collect()
        if hasattr(cls, "temp_dir") and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
        if hasattr(cls, "db_path") and os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
        os.environ.pop("DB_PATH_OVERRIDE", None)
        os.environ.pop("STORAGE_ROOT_OVERRIDE", None)

    def test_01_sanitize_short_name(self):
        """Test short_name sanitization rules."""
        self.assertEqual(sanitize_short_name("บริษัท ซีพี ออลล์ จำกัด (มหาชน)"), "merchant")
        self.assertEqual(sanitize_short_name("PTT Oil and Retail Business Public Co., Ltd."), "ptt_oil_and_retail_business_public")
        self.assertEqual(sanitize_short_name("Starbucks Coffee (Thailand)"), "starbucks_coffee_thailand")
        self.assertEqual(sanitize_short_name(""), "merchant")

    def test_02_new_merchant_auto_discovery_and_hold(self):
        """Test auto-discovery of new merchant and HOLD pipeline action via AI classification."""
        from unittest.mock import patch
        from src.infrastructure.external.ai.ai_service import ai_service

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
        from src.infrastructure.external.ai.ai_service import ai_service

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
        from src.infrastructure.external.ai.ai_service import ai_service

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
        os.environ["STORAGE_ROOT_OVERRIDE"] = cls.temp_dir
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
        from src.infrastructure.database.engine import dispose_all_engines
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
        os.environ.pop("STORAGE_ROOT_OVERRIDE", None)

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
        os.environ["STORAGE_ROOT_OVERRIDE"] = cls.temp_dir
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
        from src.infrastructure.database.engine import dispose_all_engines
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
        os.environ.pop("STORAGE_ROOT_OVERRIDE", None)

    def test_01_multi_page_splitting_and_chunk_assignment(self):
        """Test that PDF splitting correctly computes and records chunk_index per page in DB."""
        from unittest.mock import patch
        from src.application.pipeline.stage_1_ingestion import split_and_match
        from src.infrastructure.database import get_batch_pages

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
        from src.infrastructure.database import get_batch_pages, get_unextracted_chunks_for_batch

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
            res = extract_documents(batch_id=batch_id, doc_type="expense_receipt")
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
            res = extract_documents(batch_id=batch_id, doc_type="expense_receipt")
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

    def test_03_fail_fast_when_batch_id_missing(self):
        """Verify that Stage 3, 4, 5 strictly raise ValueError when batch_id is omitted or empty."""
        from src.application.pipeline.stage_2_extraction import extract_documents, async_extract_documents
        from src.application.pipeline.stage_4_validation import validate_documents
        from src.application.pipeline.stage_3_transformation import transform_to_db

        with self.assertRaises(ValueError):
            extract_documents(batch_id=None)

        with self.assertRaises(ValueError):
            extract_documents(batch_id="")

        with self.assertRaises(ValueError):
            validate_documents(batch_id=None)

        with self.assertRaises(ValueError):
            validate_documents(batch_id="")

        with self.assertRaises(ValueError):
            transform_to_db(batch_id=None)

        with self.assertRaises(ValueError):
            transform_to_db(batch_id="")


class TestStage5DatabaseTransformation(unittest.TestCase):
    """
    Integration test suite for Stage 5 Database Transformation and AI Payload Unwrapping.
    Verifies that multi-page AI payload accurately populates extracted_documents,
    expense_receipts, and expense_receipt_items with full non-empty values.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.temp_dir = tempfile.mkdtemp()
        os.environ["STORAGE_ROOT_OVERRIDE"] = cls.temp_dir
        setup_logger("configs/settings.json")
        initialize_db_schema(drop_and_recreate=True)
        seed_initial_data()

    @classmethod
    def tearDownClass(cls):
        import shutil
        if "STORAGE_ROOT_OVERRIDE" in os.environ:
            del os.environ["STORAGE_ROOT_OVERRIDE"]
        if hasattr(cls, "temp_dir") and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_extract_page_document_payload_matching(self):
        """Test unwrapping document by logical_page_number and fallback indexing."""
        from src.application.pipeline.pipeline_helpers import extract_page_document_payload

        mock_payload = {
            "extracted_documents": [
                {
                    "logical_page_number": 1,
                    "receipt_info": {"receipt_number": "REC-001", "transaction_date": "2026-06-01"},
                    "merchant": {"name": "Grab 1", "tax_id": "1111111111111"},
                    "totals": {"net_amount": 100.0}
                },
                {
                    "logical_page_number": 2,
                    "receipt_info": {"receipt_number": "REC-002", "transaction_date": "2026-06-02"},
                    "merchant": {"name": "Grab 2", "tax_id": "2222222222222"},
                    "totals": {"net_amount": 200.0}
                }
            ],
            "_metadata": {"model_used": "gemini-3.5-flash-lite", "input_tokens": 100}
        }

        # Match page 1
        doc1 = extract_page_document_payload(mock_payload, page_number=1)
        self.assertEqual(doc1["receipt_info"]["receipt_number"], "REC-001")
        self.assertEqual(doc1["totals"]["net_amount"], 100.0)
        self.assertEqual(doc1["_metadata"]["model_used"], "gemini-3.5-flash-lite")

        # Match page 2
        doc2 = extract_page_document_payload(mock_payload, page_number=2)
        self.assertEqual(doc2["receipt_info"]["receipt_number"], "REC-002")
        self.assertEqual(doc2["totals"]["net_amount"], 200.0)

        # Single object without extracted_documents wrapper
        single_payload = {"receipt_info": {"receipt_number": "SINGLE-001"}}
        doc_single = extract_page_document_payload(single_payload, page_number=1)
        self.assertEqual(doc_single["receipt_info"]["receipt_number"], "SINGLE-001")

    def test_02_insert_relational_receipt_with_items_and_metadata(self):
        """Test insert_relational_receipt persists header and item rows with Pure SQLAlchemy 2.0."""
        from src.infrastructure.database import (
            create_batch,
            create_document,
            insert_relational_receipt,
            get_db_session,
            ExpenseReceipt,
            ExpenseReceiptItem,
            get_all_companies
        )
        from sqlalchemy import select

        comps = get_all_companies(active_only=True)
        comp_id = comps[0]["company_id"]

        batch_id = "test_batch_receipt_001"
        create_batch(batch_id=batch_id, created_by="test_user", original_filename="test.pdf", total_pages=1, storage_path="fake/path", file_hash="hash_rcpt_001", company_id=comp_id)

        doc_id = "doc_test_relational_001"
        create_document(document_id=doc_id, batch_id=batch_id, created_by="test_user", doc_type_id="expense_receipt", company_id=comp_id, status_code="PROCESSED")

        mock_ai_payload = {
            "extracted_documents": [
                {
                    "logical_page_number": 1,
                    "receipt_info": {
                        "receipt_number": "IM20260601034010",
                        "transaction_date": "2026-06-01",
                        "expense_category": "Transport",
                        "payment_method": "Credit Card"
                    },
                    "merchant": {
                        "name": "Grabtaxi (Thailand) Co., Ltd.",
                        "tax_id": "0105556090377"
                    },
                    "totals": {
                        "subtotal": 2167.8,
                        "discount": 0.0,
                        "vat_amount": 151.75,
                        "net_amount": 2319.55
                    },
                    "items": [
                        {
                            "name": "Service Fee - 01-06-2026",
                            "qty": 1,
                            "unit_price": 2167.8,
                            "total_price": 2167.8
                        }
                    ]
                }
            ]
        }

        success = insert_relational_receipt(
            document_id=doc_id,
            payload=mock_ai_payload,
            original_filename="test.pdf",
            created_by="test_user",
            company_id=comp_id,
            page_number=1
        )
        self.assertTrue(success)

        # Verify DB records
        with get_db_session() as session:
            receipt = session.scalars(select(ExpenseReceipt).filter_by(document_id=doc_id)).first()
            self.assertIsNotNone(receipt)
            self.assertEqual(receipt.merchant_name, "Grabtaxi (Thailand) Co., Ltd.")
            self.assertEqual(receipt.tax_id, "0105556090377")
            self.assertEqual(receipt.transaction_date, "2026-06-01")
            self.assertEqual(receipt.expense_category, "Transport")
            self.assertEqual(receipt.subtotal, 2167.8)
            self.assertEqual(receipt.vat_amount, 151.75)
            self.assertEqual(receipt.net_amount, 2319.55)

            items = session.scalars(select(ExpenseReceiptItem).filter_by(receipt_id=receipt.receipt_id)).all()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].item_name, "Service Fee - 01-06-2026")
            self.assertEqual(items[0].quantity, 1.0)
            self.assertEqual(items[0].unit_price, 2167.8)
            self.assertEqual(items[0].total_price, 2167.8)

    def test_03_transform_to_db_end_to_end_populates_all_tables(self):
        """Test transform_to_db full pipeline stage populates extracted_documents, receipts, and items."""
        from src.application.pipeline.stage_3_transformation import transform_to_db
        from src.infrastructure.database import (
            create_batch,
            create_page,
            get_document_by_id,
            get_all_companies,
            get_db_session,
            ExpenseReceipt,
            ExpenseReceiptItem
        )
        from src.infrastructure.external.storage.storage_manager import storage_manager
        from sqlalchemy import select

        comps = get_all_companies(active_only=True)
        comp_code = comps[0]["company_code"]
        comp_id = comps[0]["company_id"]

        batch_id = "test_batch_e2e_transform_001"
        create_batch(batch_id=batch_id, created_by="test_user", original_filename="Grab_Sample.pdf", total_pages=1, storage_path="storage/companies/C00000_SAMPLE/expense_receipt/02_raw_data/0105556090377_grab", file_hash="hash_e2e_001", company_id=comp_id)

        # Setup page image and json in isolated storage
        prep_dir = storage_manager.get_preprocess_dir(comp_code, "expense_receipt")
        os.makedirs(prep_dir, exist_ok=True)
        fake_img_path = os.path.join(prep_dir, f"{batch_id}_page_1.jpg").replace("\\", "/")
        with open(fake_img_path, "wb") as f:
            f.write(b"fake_jpg_data")

        create_page(page_id="page_e2e_001", batch_id=batch_id, page_number=1, image_path=fake_img_path, status_code="EXTRACTED")

        proc_dir = storage_manager.get_processing_dir(comp_code, "expense_receipt")
        merchant_proc_dir = os.path.join(proc_dir, "0105556090377_grab").replace("\\", "/")
        os.makedirs(merchant_proc_dir, exist_ok=True)
        json_path = os.path.join(merchant_proc_dir, f"{batch_id}_page_1.json").replace("\\", "/")

        mock_payload = {
            "extracted_documents": [
                {
                    "logical_page_number": 1,
                    "receipt_info": {
                        "receipt_number": "IM20260601034010",
                        "transaction_date": "2026-06-01",
                        "expense_category": "Transport",
                        "payment_method": "Credit Card"
                    },
                    "merchant": {
                        "name": "Grabtaxi (Thailand) Co., Ltd.",
                        "tax_id": "0105556090377"
                    },
                    "totals": {
                        "subtotal": 2167.8,
                        "discount": 0.0,
                        "vat_amount": 151.75,
                        "net_amount": 2319.55
                    },
                    "items": [
                        {
                            "name": "Service Fee - 01-06-2026",
                            "qty": 1,
                            "unit_price": 2167.8,
                            "total_price": 2167.8
                        }
                    ],
                    "extraction_metadata": {
                        "overall_confidence": 0.98,
                        "confidence_level": "HIGH",
                        "confidence_notes": "ตัวเลขชัดเจน หัวบิลและยอดรวมอ่านได้ครบถ้วน"
                    }
                }
            ],
            "_metadata": {
                "model_used": "gemini-3.5-flash-lite",
                "input_tokens": 1000,
                "output_tokens": 200,
                "cost_usd": 0.0001,
                "cost_thb": 0.0036
            }
        }
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(mock_payload, jf, ensure_ascii=False, indent=2)

        # Run Stage 5 Transform to DB
        result = transform_to_db(batch_id=batch_id, doc_type="expense_receipt", company_code=comp_code)
        self.assertEqual(result.get("imported"), 1)
        self.assertEqual(result.get("failed"), 0)

        # Assert document_controls record
        with get_db_session() as session:
            from src.infrastructure.database.models import DocumentControl
            doc = session.scalars(select(DocumentControl).filter_by(batch_id=batch_id)).first()
            self.assertIsNotNone(doc)
            self.assertEqual(doc.doc_type_id, "expense_receipt")
            self.assertEqual(doc.overall_confidence, 0.98)
            self.assertEqual(doc.confidence_level, "HIGH")
            self.assertEqual(doc.model_used, "gemini-3.5-flash-lite")

            # Assert expense_receipts
            receipt = session.scalars(select(ExpenseReceipt).filter_by(document_id=doc.document_id)).first()
            self.assertIsNotNone(receipt)
            self.assertEqual(receipt.doc_number, "IM20260601034010")
            self.assertEqual(receipt.transaction_date, "2026-06-01")
            self.assertEqual(receipt.merchant_name, "Grabtaxi (Thailand) Co., Ltd.")
            self.assertEqual(receipt.tax_id, "0105556090377")
            self.assertEqual(receipt.net_amount, 2319.55)

            # Assert expense_receipt_items
            items = session.scalars(select(ExpenseReceiptItem).filter_by(receipt_id=receipt.receipt_id)).all()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].item_name, "Service Fee - 01-06-2026")
            self.assertEqual(items[0].total_price, 2167.8)


if __name__ == "__main__":
    unittest.main()

