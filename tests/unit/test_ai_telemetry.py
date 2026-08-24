import os
import unittest
import uuid
import tempfile
import shutil
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
from src.infrastructure.persistence.connection import get_engine
from src.infrastructure.ai.ai_service import ai_service
from src.application.usecases.classifier import classify_document
from src.application.usecases.extractor import extract_document_data


class TestAiTelemetryAndIsolation(unittest.TestCase):
    """
    Test suite for AI Telemetry logging, Company tax_id uniqueness,
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
        cls.temp_dir = tempfile.mkdtemp()

        # Generate a dummy test image
        cls.dummy_img_path = os.path.join(cls.temp_dir, "test_receipt.png").replace("\\", "/")
        img = Image.new("RGB", (200, 200), color="white")
        img.save(cls.dummy_img_path)

    @classmethod
    def tearDownClass(cls):
        import gc
        # 1. Dispose engine
        try:
            get_engine().dispose()
        except Exception:
            pass
        gc.collect()

        # 2. Clean temporary database
        if hasattr(cls, "test_db_path") and os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass
        os.environ.pop("DB_PATH_OVERRIDE", None)

        # 3. Clean temporary storage directory
        if hasattr(cls, "temp_dir") and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_company_tax_id_uniqueness(self):
        """Verify that duplicate tax_id raises ValueError."""
        code1 = f"C_{uuid.uuid4().hex[:6].upper()}"
        code2 = f"C_{uuid.uuid4().hex[:6].upper()}"
        unique_tax = f"01055{uuid.uuid4().hex[:8]}"[:13]

        # First company succeeds
        c1 = create_company(
            company_code=code1,
            company_name="Unique Tax Company A",
            short_name="COMP_A",
            tax_id=unique_tax,
        )
        self.assertEqual(c1["company_code"], code1)

        # Second company with same tax_id must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            create_company(
                company_code=code2,
                company_name="Duplicate Tax Company B",
                short_name="COMP_B",
                tax_id=unique_tax,
            )
        self.assertIn("already registered", str(ctx.exception))

    def test_02_company_update_tax_id_uniqueness(self):
        """Verify updating to an existing tax_id fails."""
        code1 = f"C_{uuid.uuid4().hex[:6].upper()}"
        code2 = f"C_{uuid.uuid4().hex[:6].upper()}"
        tax1 = f"01055{uuid.uuid4().hex[:8]}"[:13]
        tax2 = f"01055{uuid.uuid4().hex[:8]}"[:13]

        c1 = create_company(company_code=code1, company_name="Comp 1", short_name="C1", tax_id=tax1)
        c2 = create_company(company_code=code2, company_name="Comp 2", short_name="C2", tax_id=tax2)

        # Attempt to update c2's tax_id to tax1 -> must return False / fail
        ok = update_company(c2["company_id"], tax_id=tax1)
        self.assertFalse(ok)

    def test_03_extract_structured_json_writes_telemetry(self):
        """Verify extract_structured_json logs into api_call_logs table."""
        rand_tax = f"9{uuid.uuid4().int % 1000000000000:012d}"
        comp = create_company(company_code=f"C_{uuid.uuid4().hex[:6]}", company_name="Telemetry Test Co", short_name="TTC", tax_id=rand_tax)
        test_comp_id = comp["company_id"]
        test_batch_id = f"batch_{uuid.uuid4().hex[:8]}"

        mock_response = MagicMock()
        mock_response.text = '{"merchant_name": "Test Store", "tax_id": "0105559999999"}'
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 150
        mock_response.usage_metadata.candidates_token_count = 50

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(ai_service, "get_client", return_value=mock_client):
            img = Image.open(self.dummy_img_path)
            payload, meta = ai_service.extract_structured_json(
                prompt="Extract data",
                images=[img],
                batch_id=test_batch_id,
                company_id=test_comp_id,
            )

            self.assertEqual(payload["merchant_name"], "Test Store")
            self.assertEqual(meta["input_tokens"], 150)
            self.assertEqual(meta["output_tokens"], 50)

        # Verify DB entry
        logs = get_api_call_logs(limit=10)
        matching_logs = [l for l in logs if l.get("batch_id") == test_batch_id]
        self.assertGreater(len(matching_logs), 0)
        self.assertEqual(matching_logs[0]["status_code"], "SUCCESS")
        self.assertEqual(matching_logs[0]["input_tokens"], 150)
        self.assertEqual(matching_logs[0]["output_tokens"], 50)
        self.assertEqual(matching_logs[0]["company_id"], test_comp_id)

    def test_04_generate_raw_content_writes_telemetry(self):
        """Verify generate_raw_content logs into api_call_logs table."""
        test_batch_id = f"batch_raw_{uuid.uuid4().hex[:8]}"

        mock_response = MagicMock()
        mock_response.text = "shopee"
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 80
        mock_response.usage_metadata.candidates_token_count = 5

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(ai_service, "get_client", return_value=mock_client):
            result = ai_service.generate_raw_content(
                prompt="Classify image",
                batch_id=test_batch_id,
            )
            self.assertEqual(result, "shopee")

        # Verify DB entry
        logs = get_api_call_logs(limit=10)
        matching_logs = [l for l in logs if l.get("batch_id") == test_batch_id]
        self.assertGreater(len(matching_logs), 0)
        self.assertEqual(matching_logs[0]["status_code"], "SUCCESS")
        self.assertEqual(matching_logs[0]["input_tokens"], 80)
        self.assertEqual(matching_logs[0]["output_tokens"], 5)


if __name__ == "__main__":
    unittest.main()
