"""Unit tests for JSON Template Evaluator and Dynamic Record Transformer.

Tests dot-notation traversal, summary vs line-item granularity, missing key fallbacks,
and fail-fast error handling for missing template configs.
100% In-memory, zero network or database dependencies.
"""

import os
import json
import pytest
from src.domain.services.template_evaluator import get_nested_value, transform_data


def test_get_nested_value_deep_traversal():
    """Test deep dot-notation traversal of nested dictionary keys."""
    data = {
        "merchant": {"name": "Test Store", "address": {"city": "Bangkok"}},
        "totals": {"financial": {"net_amount": 1250.75}}
    }

    assert get_nested_value(data, "merchant.name") == "Test Store"
    assert get_nested_value(data, "merchant.address.city") == "Bangkok"
    assert get_nested_value(data, "totals.financial.net_amount") == 1250.75


def test_get_nested_value_missing_and_none():
    """Test fallback to empty string when keys are missing or input is None."""
    data = {"merchant": {"name": "Test Store"}}

    assert get_nested_value(None, "merchant.name") == ""
    assert get_nested_value(data, "merchant.missing_key") == ""
    assert get_nested_value(data, "invalid.path.to.field") == ""


def test_transform_data_summary_granularity(tmp_path):
    """Test transforming hierarchical JSON data using summary granularity."""
    template_config = {
        "granularity": "summary",
        "columns": {
            "Vendor": "merchant.name",
            "TaxID": "merchant.tax_id",
            "Total": "totals.net_amount"
        }
    }
    template_file = tmp_path / "summary_template.json"
    with open(template_file, "w", encoding="utf-8") as f:
        json.dump(template_config, f)

    extracted_data = {
        "merchant": {"name": "CP All PCL", "tax_id": "0107542000011"},
        "totals": {"net_amount": 350.0}
    }

    rows = transform_data(extracted_data, str(template_file))

    assert len(rows) == 1
    assert rows[0]["Vendor"] == "CP All PCL"
    assert rows[0]["TaxID"] == "0107542000011"
    assert rows[0]["Total"] == 350.0


def test_transform_data_line_items_granularity(tmp_path):
    """Test transforming hierarchical JSON data with line items into multiple rows."""
    template_config = {
        "granularity": "line_items",
        "columns": {
            "Vendor": "merchant.name",
            "ItemDescription": "item.name",
            "Quantity": "item.quantity",
            "UnitPrice": "item.unit_price",
            "Amount": "item.total_price",
            "NetTotal": "totals.net_amount"
        }
    }
    template_file = tmp_path / "items_template.json"
    with open(template_file, "w", encoding="utf-8") as f:
        json.dump(template_config, f)

    extracted_data = {
        "merchant": {"name": "HomePro"},
        "totals": {"net_amount": 1500.0},
        "items": [
            {"name": "Light Bulb", "quantity": 2, "unit_price": 250.0, "total_price": 500.0},
            {"name": "Power Strip", "quantity": 1, "unit_price": 1000.0, "total_price": 1000.0}
        ]
    }

    rows = transform_data(extracted_data, str(template_file))

    assert len(rows) == 2
    assert rows[0]["Vendor"] == "HomePro"
    assert rows[0]["ItemDescription"] == "Light Bulb"
    assert rows[0]["Amount"] == 500.0
    assert rows[0]["NetTotal"] == 1500.0

    assert rows[1]["Vendor"] == "HomePro"
    assert rows[1]["ItemDescription"] == "Power Strip"
    assert rows[1]["Amount"] == 1000.0


def test_transform_data_line_items_fallback_empty_items(tmp_path):
    """Test line items granularity with empty items array produces one row with empty item fields."""
    template_config = {
        "granularity": "line_items",
        "columns": {
            "Vendor": "merchant.name",
            "ItemDescription": "item.name",
            "NetTotal": "totals.net_amount"
        }
    }
    template_file = tmp_path / "empty_items_template.json"
    with open(template_file, "w", encoding="utf-8") as f:
        json.dump(template_config, f)

    extracted_data = {
        "merchant": {"name": "Shell Gas Station"},
        "totals": {"net_amount": 800.0},
        "items": []
    }

    rows = transform_data(extracted_data, str(template_file))

    assert len(rows) == 1
    assert rows[0]["Vendor"] == "Shell Gas Station"
    assert rows[0]["ItemDescription"] == ""
    assert rows[0]["NetTotal"] == 800.0


def test_transform_data_missing_template_file_raises_filenotfound():
    """Test that missing template path fails fast by raising FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        transform_data({"test": 123}, "non_existent_template_path.json")
