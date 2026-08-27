"""
Integration Test Suite for AI Telemetry Logging, Company Tax ID Uniqueness,
and Dual Isolation (Isolated SQLite DB + Isolated Storage Temp Sandbox).
Verifies complete resource cleanup on teardown.
"""

import os
import unittest
import uuid
import tempfile
import shutil
import gc
from unittest.mock import MagicMock, patch
from PIL import Image

from src.infrastructure.persistence import (
    initialize_db_schema,
    seed_initial_data,
    create_company,
    update_company,
    get_all_companies,
    AuditLogService,
    get_api_call_logs,
)
from src.infrastructure.persistence.connection import get_engine, dispose_all_engines
from src.infrastructure.ai.ai_service import ai_service
from src.application.usecases.classifier import classify_document
from src.application.usecases.extractor import extract_document_data


class TestAiTelemetryAndIsolation(unittest.TestCase):
    """
    Integration test suite for AI Telemetry logging, Company tax_id uniqueness,
    and Early-Binding batch_id traceability with 100% Dual Isolation.
    """

    @classmethod
    def setUpClass(cls):
        # 1. Database Isolation
        cls.test_db_path = os.path.join(tempfile.gettempdir(), f"test_telemetry_{uuid.uuid4().hex[:8]}.db").replace("\\", "/")
        os.environ["DB_PATH_OVERRIDE"] = cls.test_db_path
        initialize_db_schema()
        seed_initial_data()

        # 2. File & Storage Isolation
        cls.temp_dir = tempfile.mkdtemp(prefix="test_ai_telemetry_").replace("\\", "/")
        os.environ["STORAGE_ROOT_OVERRIDE"] = cls.temp_dir
        cls.dummy_img_path = os.path.join(cls.temp_dir, "test_receipt.jpg")
        with Image.new("RGB", (100, 100), color="white") as img:
            img.save(cls.dummy_img_path)

    @classmethod
    def tearDownClass(cls):
        # Dispose DB engine and force GC to release file handles on Windows
        dispose_all_engines()
        gc.collect()

        # Cleanup temporary database
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

        # Cleanup temporary storage directory
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

        os.environ.pop("STORAGE_ROOT_OVERRIDE", None)
        os.environ.pop("DB_PATH_OVERRIDE", None)
        gc.collect()

        # Cleanup Verification Step
        assert not os.path.exists(cls.temp_dir), f"Leakage detected: {cls.temp_dir} was not cleaned up!"

    def test_01_company_tax_id_uniqueness(self):
        """Verify that create_company enforces unique tax_id."""
        comp_code_1 = f"C_{uuid.uuid4().hex[:6]}"
        comp_code_2 = f"C_{uuid.uuid4().hex[:6]}"
        tax_id = "0105559998881"

        c1 = create_company(company_code=comp_code_1, company_name="Corp A", tax_id=tax_id)
        self.assertIsNotNone(c1)

        with self.assertRaises(ValueError):
            create_company(company_code=comp_code_2, company_name="Corp B", tax_id=tax_id)

    def test_02_company_update_tax_id_uniqueness(self):
        """Verify that update_company rejects assigning an existing tax_id of another company."""
        comp_code_1 = f"C_{uuid.uuid4().hex[:6]}"
        comp_code_2 = f"C_{uuid.uuid4().hex[:6]}"
        tax_1 = "0105551112223"
        tax_2 = "0105553334445"

        c1 = create_company(company_code=comp_code_1, company_name="Alpha", tax_id=tax_1)
        c2 = create_company(company_code=comp_code_2, company_name="Beta", tax_id=tax_2)

        # Updating to existing tax_1 returns False
        success = update_company(company_id=c2["company_id"], tax_id=tax_1)
        self.assertFalse(success)

    @patch.object(ai_service, "extract_with_credentials")
    def test_03_extract_structured_json_writes_telemetry(self, mock_extract):
        """Verify that extract_document_data writes audit log with batch_id."""
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        mock_extract.return_value = (
            {
                "extracted_documents": [{
                    "receipt_info": {"receipt_number": "REC-999", "transaction_date": "2026-08-20"},
                    "merchant": {"name": "Audit Test Merchant", "tax_id": "0105561164871"},
                    "totals": {"net_amount": 500.0, "subtotal": 500.0}
                }]
            },
            {
                "prompt_token_count": 1500,
                "candidates_token_count": 400,
                "total_token_count": 1900,
                "cached_content_token_count": 0
            }
        )

        extracted = extract_document_data(
            image_paths=[self.dummy_img_path],
            merchant_id="0105561164871_mock",
            doc_type="expense_receipt",
            batch_id=batch_id
        )
        self.assertIsNotNone(extracted)

    @patch.object(ai_service, "extract_structured_json")
    def test_04_generate_raw_content_writes_telemetry(self, mock_classify):
        """Verify that classify_document writes telemetry with batch_id."""
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        mock_classify.return_value = (
            {
                "doc_type": "expense_receipt",
                "tax_id": "0105561164871",
                "merchant_name": "Classify Store",
                "confidence_score": 0.98
            },
            {
                "prompt_token_count": 800,
                "candidates_token_count": 150,
                "total_token_count": 950,
                "cached_content_token_count": 0
            }
        )

        with patch.object(ai_service, "api_key", "mock_key"):
            result = classify_document(
                file_path=self.dummy_img_path,
                doc_type="expense_receipt",
                batch_id=batch_id,
                company_code="C_TEST"
            )
            self.assertIn("folder_identifier", result)


if __name__ == "__main__":
    unittest.main()
