"""
Unit tests for Business Domain Engines, Policies, Validators, and Cost Estimation.
Uses pytest parameterization and clean AAA pattern.
"""

import os
import tempfile
import uuid
import pytest

from src.application.dtos.document_dto import ExtractedReceiptPayloadModel, ReceiptItemModel, TotalsModel
from src.domain.policies.validators import (
    DateNormalizationValidator,
    FinancialMathValidator,
    ValidationStrategyEngine,
)
from src.infrastructure.ai.cost_estimator import calculate_api_cost, format_cost_display
from src.infrastructure.ai.ai_service import AIService
from src.infrastructure.exporters.registry import get_exporter, list_exporters


# ==============================================================================
# Domain Policies & Validators Tests
# ==============================================================================

def test_pydantic_model_sanitization():
    """Test Pydantic v2 data model parsing and string-to-float sanitization."""
    # Arrange
    payload = ExtractedReceiptPayloadModel(
        receipt_info={"receipt_number": "INV-001", "transaction_date": "2569-08-15"},
        merchant={"name": "Test Store", "tax_id": "0105561164871"},
        items=[
            ReceiptItemModel(name="Item A", qty="2", unit_price="100.50", total_price="201.00")
        ],
        totals=TotalsModel(subtotal="201.00", discount="0.00", vat_amount="14.07", net_amount="215.07")
    )

    # Assert
    assert payload.receipt_info.receipt_number == "INV-001"
    assert payload.items[0].total_price == 201.0
    assert payload.totals.net_amount == 215.07


def test_date_normalization_validator():
    """Test Buddhist Era (BE) to Christian Era (AD) date conversion in Domain Policy."""
    # Arrange
    validator = DateNormalizationValidator()
    payload = {"receipt_info": {"transaction_date": "2569-08-21"}}
    
    # Act
    updated, needs_review, reasons = validator.validate(payload)
    
    # Assert
    assert needs_review is False
    assert updated["receipt_info"]["transaction_date"] == "2026-08-21"


@pytest.mark.parametrize("totals_data, expected_needs_review", [
    ({"subtotal": 100.0, "discount": 10.0, "vat_amount": 6.3, "net_amount": 96.3}, False),
    ({"subtotal": 100.0, "discount": 0.0, "vat_amount": 7.0, "net_amount": 107.0}, False),
    ({"subtotal": 100.0, "discount": 0.0, "vat_amount": 7.0, "net_amount": 500.0}, True),  # Math mismatch
    ({"subtotal": 0.0, "discount": 0.0, "vat_amount": 0.0, "net_amount": 0.0}, False),
])
def test_financial_math_validator_parameterized(totals_data, expected_needs_review):
    """Test financial math discrepancy detection across various balanced & unbalanced totals."""
    # Arrange
    validator = FinancialMathValidator()
    payload = {"totals": totals_data}

    # Act
    _, needs_review, reasons = validator.validate(payload)

    # Assert
    assert needs_review is expected_needs_review
    if expected_needs_review:
        assert len(reasons) > 0


def test_validation_strategy_engine():
    """Test execution of validation strategy engine pipeline."""
    # Arrange
    engine = ValidationStrategyEngine()
    payload = {
        "receipt_info": {"transaction_date": "2569-08-21"},
        "merchant": {"tax_id": "0105561164871"},
        "totals": {"subtotal": 100.0, "discount": 0.0, "vat_amount": 7.0, "net_amount": 107.0}
    }
    
    # Act
    updated_payload, needs_review, reasons = engine.run_validation(
        payload, context={"source": "mock_source", "allowed_tax_ids": ["0105561164871"]}
    )
    
    # Assert
    assert needs_review is False
    assert updated_payload["receipt_info"]["transaction_date"] == "2026-08-21"


# ==============================================================================
# AI Token Pricing & Cost Estimator Engine Tests
# ==============================================================================

@pytest.mark.parametrize("provider, model, in_tok, out_tok, tier, exp_free, exp_cost_usd", [
    ("gemini", "gemini-3.5-flash", 1000, 500, "paid", 0, 0.000225),
    ("gemini", "gemini-3.5-flash", 1000, 500, "free", 1, 0.0),
    ("openai", "gpt-4o", 2000, 1000, "paid", 0, 0.0150),
])
def test_cost_estimator_parameterized(provider, model, in_tok, out_tok, tier, exp_free, exp_cost_usd):
    """Test AI model pricing calculations across free and paid tiers."""
    # Arrange & Act
    res = calculate_api_cost(
        provider=provider,
        model_name=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        override_tier=tier
    )

    # Assert
    assert res["is_free_tier"] == exp_free
    assert pytest.approx(res["cost_usd"], rel=1e-3) == exp_cost_usd
    if exp_free == 1:
        assert res["nominal_value_usd"] > 0


def test_format_cost_display():
    """Verify display formatting for both Paid and Free tiers."""
    # Arrange & Act
    paid_str = format_cost_display(cost_usd=0.000225, cost_thb=0.0081, is_free_tier=0)
    free_str = format_cost_display(cost_usd=0.0, cost_thb=0.0, is_free_tier=1, nominal_value_usd=0.000225)

    # Assert
    assert "$0.0002" in paid_str
    assert "THB" in paid_str
    assert "FREE TIER" in free_str
    assert "nominal" in free_str


# ==============================================================================
# AI Service & Exporter Strategy Tests
# ==============================================================================

def test_ai_service_initialization():
    """Test AIService initialization and configuration loading."""
    # Arrange & Act
    service = AIService()

    # Assert
    assert service.active_provider == "gemini"
    assert service.max_retries >= 1
    assert service.default_model is not None


def test_exporter_registry_lookup():
    """Test retrieving registered exporter strategy instances."""
    # Arrange & Act
    exp_summary = get_exporter("expense_receipt", "google_sheet_summary")
    exp_pv = get_exporter("expense_receipt", "express_pv")
    all_exporters = list_exporters("expense_receipt")

    # Assert
    assert exp_summary is not None
    assert exp_pv is not None
    assert exp_pv.encoding == "cp874"
    assert len(all_exporters) >= 3


def test_exporter_strategy_export():
    """Test BaseOutputExporter export() writing both CSV and JSON."""
    # Arrange
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
        # Act
        res = exporter.export([sample_doc], base_path, export_csv=True, export_json=True)
        
        # Assert
        assert "csv" in res
        assert "json" in res
        assert os.path.exists(res["csv"])
        assert os.path.exists(res["json"])
    finally:
        if os.path.exists(f"{base_path}.csv"):
            os.remove(f"{base_path}.csv")
        if os.path.exists(f"{base_path}.json"):
            os.remove(f"{base_path}.json")


def test_express_pv_thai_encoding():
    """Test Express PV exporter running numbers and cp874 compatibility."""
    # Arrange
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
        # Act
        res = exporter.export(sample_docs, base_path, export_csv=True, export_json=False)
        
        # Assert
        assert "csv" in res
        csv_path = res["csv"]
        
        with open(csv_path, "r", encoding="cp874") as f:
            content = f.read()
            assert "ร้านค้าทดสอบภาษาไทย" in content
            assert "PV2608-" in content
    finally:
        if os.path.exists(f"{base_path}.csv"):
            os.remove(f"{base_path}.csv")
