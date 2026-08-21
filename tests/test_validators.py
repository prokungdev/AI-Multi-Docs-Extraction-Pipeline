import unittest
from src.core.models import ExtractedReceiptPayloadModel, ReceiptItemModel, TotalsModel
from src.core.validators import (
    DateNormalizationValidator,
    TaxIDValidator,
    FinancialMathValidator,
    ValidationStrategyEngine
)

class TestValidators(unittest.TestCase):

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

if __name__ == "__main__":
    unittest.main()
