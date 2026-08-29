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


def test_system_settings_model_pipeline_folders_default():
    """Test SystemSettingsModel populates canonical pipeline_folders by default when omitted."""
    from src.application.dtos.settings_dto import SystemSettingsModel
    from src.infrastructure.core.constants import PipelineStageFolder

    minimal_valid_settings = {
        "logging": {"logs_dir": "logs"},
        "image_processing": {
            "supported_input_extensions": [".pdf", ".jpg"],
            "processing_format": "jpg",
            "jpeg_quality": 85,
            "max_dimension": 1800,
            "dpi": 150,
            "split_filename_pattern": "{doc_type}_{tax_id}_{original_filename}_{batch_id}_p{page_no}",
            "archive_filename_pattern": "{doc_type}_{tax_id}_{doc_no}_{batch_id}_p{page_no}",
        },
        "validation_thresholds": {
            "confidence_high": 0.85,
            "confidence_low": 0.50,
            "confidence_review": 0.70,
            "financial_tolerance": 0.05,
        },
        "database": {"active_driver": "sqlite"},
    }

    model = SystemSettingsModel.model_validate(minimal_valid_settings)
    assert model.pipeline_folders == PipelineStageFolder.list_all()
    assert len(model.pipeline_folders) == 6

