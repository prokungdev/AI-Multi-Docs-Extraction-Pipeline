import unittest
from src.core.models import ExtractedReceiptPayloadModel, ReceiptItemModel, TotalsModel
from src.core.validators import (
    DateNormalizationValidator,
    TaxIDValidator,
    FinancialMathValidator,
    ValidationStrategyEngine,
)
from src.core.cost_estimator import calculate_api_cost, format_cost_display


class TestValidators(unittest.TestCase):
    """
    Test suite for Pydantic v2 data models, Thai date normalization (BE->AD), and Math Balance checks.
    """

    def test_01_pydantic_model_sanitization(self):
        """Test Pydantic v2 data model parsing and string-to-float sanitization."""
        payload = ExtractedReceiptPayloadModel(
            receipt_info={"receipt_number": "INV-001", "transaction_date": "2569-08-15"},
            merchant={"name": "Test Store", "tax_id": "0105561164871"},
            items=[
                ReceiptItemModel(name="Item A", qty="2", unit_price="100.50", total_price="201.00")
            ],
            totals=TotalsModel(subtotal="201.00", discount="0.00", vat_amount="14.07", net_amount="215.07")
        )

        self.assertEqual(payload.receipt_info.receipt_number, "INV-001")
        self.assertEqual(payload.items[0].total_price, 201.0)
        self.assertEqual(payload.totals.net_amount, 215.07)

    def test_02_date_normalization_validator(self):
        """Test Buddhist Era (BE) to Christian Era (AD) date conversion."""
        validator = DateNormalizationValidator()
        payload = {"receipt_info": {"transaction_date": "2569-08-21"}}
        
        updated, needs_review, reasons = validator.validate(payload)
        self.assertFalse(needs_review)
        self.assertEqual(updated["receipt_info"]["transaction_date"], "2026-08-21")

    def test_03_financial_math_validator(self):
        """Test financial math discrepancy detection strategy."""
        validator = FinancialMathValidator()
        valid_payload = {"totals": {"subtotal": 100.0, "discount": 10.0, "vat_amount": 6.3, "net_amount": 96.3}}
        _, needs_review, _ = validator.validate(valid_payload)
        self.assertFalse(needs_review)

        invalid_payload = {"totals": {"subtotal": 100.0, "discount": 0.0, "vat_amount": 7.0, "net_amount": 500.0}}
        _, needs_review, reasons = validator.validate(invalid_payload)
        self.assertTrue(needs_review)
        self.assertGreater(len(reasons), 0)

    def test_04_validation_strategy_engine(self):
        """Test execution of validation strategy engine pipeline."""
        engine = ValidationStrategyEngine()
        payload = {
            "receipt_info": {"transaction_date": "2569-08-21"},
            "merchant": {"tax_id": "0105561164871"},
            "totals": {"subtotal": 100.0, "discount": 0.0, "vat_amount": 7.0, "net_amount": 107.0}
        }
        
        updated_payload, needs_review, reasons = engine.run_validation(
            payload, context={"source": "mock_source", "allowed_tax_ids": ["0105561164871"]}
        )
        self.assertFalse(needs_review)
        self.assertEqual(updated_payload["receipt_info"]["transaction_date"], "2026-08-21")


class TestCostEstimatorEngine(unittest.TestCase):
    """
    Test suite for AI Token Pricing and Free/Paid Tier Metering engine.
    """

    def test_01_gemini_flash_paid_tier(self):
        """Calculate Gemini Flash token cost in Paid Tier."""
        res = calculate_api_cost(
            provider="gemini",
            model_name="gemini-3.5-flash",
            input_tokens=1000,
            output_tokens=500,
            override_tier="paid"
        )
        self.assertEqual(res["is_free_tier"], 0)
        self.assertAlmostEqual(res["cost_usd"], 0.000225, places=6)
        self.assertAlmostEqual(res["nominal_value_usd"], 0.000225, places=6)
        self.assertAlmostEqual(res["cost_thb"], 0.000225 * res["exchange_rate_thb"], places=4)

    def test_02_gemini_flash_free_tier(self):
        """Verify cost is $0.00 in Free Tier while preserving nominal market value."""
        res = calculate_api_cost(
            provider="gemini",
            model_name="gemini-3.5-flash",
            input_tokens=1000,
            output_tokens=500,
            override_tier="free"
        )
        self.assertEqual(res["is_free_tier"], 1)
        self.assertEqual(res["cost_usd"], 0.0)
        self.assertEqual(res["cost_thb"], 0.0)
        self.assertAlmostEqual(res["nominal_value_usd"], 0.000225, places=6)

    def test_03_gpt4o_paid_tier(self):
        """Verify OpenAI model pricing calculation."""
        res = calculate_api_cost(
            provider="openai",
            model_name="gpt-4o",
            input_tokens=2000,
            output_tokens=1000,
            override_tier="paid"
        )
        self.assertEqual(res["is_free_tier"], 0)
        self.assertAlmostEqual(res["cost_usd"], 0.0150, places=4)
        self.assertAlmostEqual(res["cost_thb"], 0.0150 * res["exchange_rate_thb"], places=3)

    def test_04_format_cost_display(self):
        """Verify display formatting for both Paid and Free tiers."""
        paid_str = format_cost_display(cost_usd=0.000225, cost_thb=0.0081, is_free_tier=0)
        self.assertIn("$0.0002", paid_str)
        self.assertIn("THB", paid_str)

        free_str = format_cost_display(cost_usd=0.0, cost_thb=0.0, is_free_tier=1, nominal_value_usd=0.000225)
        self.assertIn("FREE TIER", free_str)
        self.assertIn("nominal", free_str)


class TestAIServiceAndExporters(unittest.TestCase):
    """
    Test suite for Unified AIService and Exporter Strategy implementations.
    """

    def test_01_ai_service_initialization(self):
        """Test AIService initialization and configuration loading."""
        from src.core.ai_service import AIService
        service = AIService()
        self.assertEqual(service.active_provider, "gemini")
        self.assertGreaterEqual(service.max_retries, 1)
        self.assertIsNotNone(service.default_model)

    def test_02_exporter_registry_lookup(self):
        """Test retrieving registered exporter strategy instances."""
        from src.core.exporters.registry import get_exporter, list_exporters
        exp_summary = get_exporter("expense_receipt", "google_sheet_summary")
        self.assertIsNotNone(exp_summary)

        exp_pv = get_exporter("expense_receipt", "express_pv")
        self.assertIsNotNone(exp_pv)
        self.assertEqual(exp_pv.encoding, "cp874")

        all_exporters = list_exporters("expense_receipt")
        self.assertGreaterEqual(len(all_exporters), 3)

    def test_03_exporter_strategy_export(self):
        """Test BaseOutputExporter export() writing both CSV and JSON."""
        import tempfile
        import os
        import uuid
        from src.core.exporters.registry import get_exporter

        exporter = get_exporter("expense_receipt", "google_sheet_summary")
        temp_dir = tempfile.gettempdir()
        base_path = os.path.join(temp_dir, f"test_exp_{uuid.uuid4().hex[:8]}")

        sample_doc = {
            "payload": {
                "receipt_info": {"receipt_number": "INV-999", "transaction_date": "2026-08-20"},
                "merchant": {"name": "Test Store", "tax_id": "0105561164871"},
                "items": [{"name": "Item A", "total_price": 100.0}],
                "totals": {"subtotal": 100.0, "vat_amount": 7.0, "net_amount": 107.0}
            },
            "document_id": "doc_123",
            "domain_id": "expense_receipt",
            "original_pdf_name": "sample.pdf"
        }

        try:
            res = exporter.export([sample_doc], base_path, export_csv=True, export_json=True)
            self.assertIn("csv", res)
            self.assertIn("json", res)
            self.assertTrue(os.path.exists(res["csv"]))
            self.assertTrue(os.path.exists(res["json"]))
        finally:
            if os.path.exists(f"{base_path}.csv"):
                os.remove(f"{base_path}.csv")
            if os.path.exists(f"{base_path}.json"):
                os.remove(f"{base_path}.json")

    def test_04_express_pv_thai_encoding(self):
        """Test Express PV exporter running numbers and cp874 compatibility."""
        import tempfile
        import os
        import uuid
        from src.core.exporters.registry import get_exporter

        exporter = get_exporter("expense_receipt", "express_pv")
        temp_dir = tempfile.gettempdir()
        base_path = os.path.join(temp_dir, f"test_pv_{uuid.uuid4().hex[:8]}")

        sample_docs = [
            {
                "data_payload": {
                    "totals": {"subtotal": 500.0, "vat_amount": 35.0, "net_amount": 535.0}
                },
                "doc_number": "REC-001",
                "entity_name": "ร้านค้าทดสอบภาษาไทย",
                "tax_id": "0105561164871",
                "source_id": "NO_TAXID",
                "doc_date": "2026-08-21"
            }
        ]

        try:
            res = exporter.export(sample_docs, base_path, export_csv=True, export_json=False)
            self.assertIn("csv", res)
            csv_path = res["csv"]
            
            # Verify CP874 readability
            with open(csv_path, "r", encoding="cp874") as f:
                content = f.read()
                self.assertIn("ร้านค้าทดสอบภาษาไทย", content)
                self.assertIn("PV2608-", content)
        finally:
            if os.path.exists(f"{base_path}.csv"):
                os.remove(f"{base_path}.csv")


if __name__ == "__main__":
    unittest.main()

