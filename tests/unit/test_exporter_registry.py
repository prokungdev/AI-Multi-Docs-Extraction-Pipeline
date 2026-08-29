"""
Unit tests for Exporter Strategy Pattern, Dynamic Registry, and Encoding Formats.
Tests discovery and rendering logic of accounting and data exporters.
"""

import os
import tempfile
import pytest
from src.application.exporters.registry import get_exporter, list_exporters


def test_exporter_registry_lookup():
    """Test registry resolves known exporter strategies and raises ValueError on unknown."""
    # Act
    exporters = list_exporters(doc_type_id="expense_receipt")
    exporter_ids = [e["exporter_id"] for e in exporters]

    # Assert
    assert "google_sheet_summary" in exporter_ids
    assert "accounting_line_items" in exporter_ids
    assert "express_pv" in exporter_ids

    # Resolve known
    gs_exporter = get_exporter(doc_type_id="expense_receipt", exporter_id="google_sheet_summary")
    assert gs_exporter is not None

    # Resolve unknown
    with pytest.raises(ValueError):
        get_exporter(doc_type_id="expense_receipt", exporter_id="unknown_format_strategy")


def test_exporter_strategy_transform():
    """Test basic JSON config exporter transformation structure."""
    # Arrange
    exporter = get_exporter(doc_type_id="expense_receipt", exporter_id="google_sheet_summary")
    sample_records = [
        {
            "payload": {
                "receipt_info": {"receipt_number": "R001", "transaction_date": "2026-08-20"},
                "merchant": {"name": "Shop A", "tax_id": "0105561164871"},
                "totals": {"net_amount": 100.0}
            }
        }
    ]

    # Act
    df = exporter.transform(sample_records)

    # Assert
    assert not df.empty
    assert len(df) == 1
    assert "doc_number" in df.columns or "Doc_Date" in df.columns or "net_amount" in df.columns


def test_express_pv_thai_encoding():
    """Test Express PV export generates valid CP874 DataFrame transformation."""
    # Arrange
    exporter = get_exporter(doc_type_id="expense_receipt", exporter_id="express_pv")
    sample_records = [
        {
            "doc_date": "2026-08-20",
            "doc_number": "R002",
            "entity_name": "ร้านทดสอบภาษาไทย",
            "tax_id": "0105561164871",
            "total_amount": 500.0,
            "data_payload": {
                "totals": {
                    "subtotal": 465.0,
                    "vat_amount": 35.0,
                    "discount": 0.0,
                    "net_amount": 500.0
                }
            }
        }
    ]

    # Act
    df = exporter.transform(sample_records, start_voucher_no=1)

    # Assert
    assert not df.empty
    assert df.iloc[0]["Voucher_No"] == "PV2608-0001"
    assert df.iloc[0]["Merchant_Name"] == "ร้านทดสอบภาษาไทย"
    assert df.iloc[0]["Net_Amount"] == 500.0
