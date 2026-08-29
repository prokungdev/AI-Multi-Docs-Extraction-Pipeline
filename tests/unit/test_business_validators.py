"""
Unit tests for Business Domain Policies and Validation Strategy Engines.
Tests financial math validation, VAT integrity, date normalization policies, and review flag routing.
"""

import pytest
from src.domain.policies.financial_rules import (
    DateNormalizationValidator,
    FinancialMathValidator,
    ValidationStrategyEngine,
)


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
    ({"subtotal": 100.0, "discount": 0.0, "vat_amount": 7.0, "net_amount": 200.0}, True),  # Math mismatch
    ({"subtotal": 100.0, "discount": 0.0, "vat_amount": 0.0, "net_amount": 100.0}, False),
])
def test_financial_math_validator_parameterized(totals_data, expected_needs_review):
    """Test financial calculation validation and discrepancy detection."""
    # Arrange
    validator = FinancialMathValidator()
    payload = {"totals": totals_data}

    # Act
    updated, needs_review, reasons = validator.validate(payload)

    # Assert
    assert needs_review is expected_needs_review
    if expected_needs_review:
        assert len(reasons) > 0


def test_validation_strategy_engine():
    """Test ValidationStrategyEngine pipeline execution across multiple validators."""
    # Arrange
    engine = ValidationStrategyEngine([
        DateNormalizationValidator(),
        FinancialMathValidator()
    ])
    payload = {
        "receipt_info": {"transaction_date": "2568-01-01"},
        "totals": {"subtotal": 50.0, "discount": 0.0, "vat_amount": 3.5, "net_amount": 53.5}
    }

    # Act
    updated, needs_review, reasons = engine.run_validation(payload)

    # Assert
    assert needs_review is False
    assert updated["receipt_info"]["transaction_date"] == "2025-01-01"
    assert len(reasons) == 0
