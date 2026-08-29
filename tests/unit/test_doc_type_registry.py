"""Unit tests for Domain Document Types Registry (doc_types)."""

import pytest
from src.infrastructure.core.constants import DocTypeId
from src.domain.doc_types import (
    DocTypeRegistry,
    BaseDocType,
    ExpenseReceiptDocType,
    TaxInvoiceDocType,
    WithholdingTaxDocType,
    get_doc_type,
    list_doc_types,
    get_active_doc_types,
    is_doc_type_active,
    get_default_doc_type,
)


def test_registry_contains_all_builtin_doc_types():
    """Verifies that all 3 built-in doc types are registered."""
    all_types = list_doc_types()
    assert len(all_types) >= 3

    ids = [dt.doc_type_id.value for dt in all_types]
    assert DocTypeId.EXPENSE_RECEIPT.value in ids
    assert DocTypeId.TAX_INVOICE.value in ids
    assert DocTypeId.WITHHOLDING_TAX.value in ids


def test_get_doc_type_by_enum_and_string():
    """Verifies retrieval via DocTypeId enum and case-insensitive string."""
    dt1 = get_doc_type(DocTypeId.EXPENSE_RECEIPT)
    assert isinstance(dt1, ExpenseReceiptDocType)
    assert dt1.doc_type_id == DocTypeId.EXPENSE_RECEIPT

    dt2 = get_doc_type("expense_receipt")
    assert dt2 is dt1

    dt3 = get_doc_type("TAX_INVOICE")
    assert isinstance(dt3, TaxInvoiceDocType)


def test_unknown_doc_type_fails_fast():
    """Verifies that querying an unknown document type raises KeyError immediately."""
    with pytest.raises(KeyError) as exc_info:
        get_doc_type("unknown_document_type")

    assert "unknown_document_type" in str(exc_info.value)
    assert "Valid registered document types are" in str(exc_info.value)


def test_doc_type_assets_loading():
    """Verifies that each doc_type correctly loads prompt and schema assets from disk."""
    for dt in list_doc_types():
        # 1. Classify prompt & schema
        cls_prompt = dt.get_classify_prompt()
        assert isinstance(cls_prompt, str) and len(cls_prompt) > 0

        cls_schema = dt.get_classify_schema()
        assert isinstance(cls_schema, dict) and "properties" in cls_schema

        # 2. Extract prompt, schema, rules
        ext_prompt = dt.get_extract_prompt()
        assert isinstance(ext_prompt, str) and len(ext_prompt) > 0

        ext_schema = dt.get_extract_schema()
        assert isinstance(ext_schema, dict) and "properties" in ext_schema

        ext_rules = dt.get_extract_rules()
        assert isinstance(ext_rules, dict)


def test_doc_type_to_dict_and_active_list():
    """Verifies serialization and active list helper."""
    active_types = get_active_doc_types()
    assert len(active_types) >= 3
    for item in active_types:
        assert "doc_type_id" in item
        assert "display_name" in item
        assert "is_active" in item
        assert "sort_order" in item


def test_is_doc_type_active_and_default():
    """Verifies active status checker and default doc type."""
    assert is_doc_type_active(DocTypeId.EXPENSE_RECEIPT) is True
    assert is_doc_type_active("tax_invoice") is True
    assert is_doc_type_active("non_existent_type") is False

    assert get_default_doc_type() == DocTypeId.EXPENSE_RECEIPT.value


def test_doc_type_get_stage_folders_default():
    """Verifies that all built-in document types return standard 6 stage folders by default."""
    from src.infrastructure.core.constants import PipelineStageFolder

    canonical_folders = PipelineStageFolder.list_all()
    assert len(canonical_folders) == 6
    assert canonical_folders == [
        "01_drop_zone",
        "02_raw_data",
        "03_preprocess",
        "04_processing",
        "05_archive",
        "06_output",
    ]

    for dt in list_doc_types():
        stages = dt.get_stage_folders()
        assert stages == canonical_folders


def test_doc_type_custom_stage_folders_override():
    """Verifies that a custom DocType subclass can cleanly override stage folders without affecting others."""
    from src.domain.doc_types.base import BaseDocType

    class CustomStatementDocType(BaseDocType):
        doc_type_id = DocTypeId.EXPENSE_RECEIPT
        display_name = "Custom Statement"

        def get_stage_folders(self):
            return ["01_drop_zone", "02_raw_data", "04_reconciliation", "05_archive"]

    custom_dt = CustomStatementDocType()
    custom_stages = custom_dt.get_stage_folders()

    assert custom_stages == ["01_drop_zone", "02_raw_data", "04_reconciliation", "05_archive"]
    assert "03_preprocess" not in custom_stages
    assert "04_reconciliation" in custom_stages

