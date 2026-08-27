"""
Unit tests for Application Layer Pydantic v2 DTOs and Data Models.
Tests schema validation, type casting, default fallbacks, and structure correctness.
"""

import pytest
from src.application.dtos.document_dto import ExtractedReceiptPayloadModel, ReceiptItemModel, TotalsModel


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
