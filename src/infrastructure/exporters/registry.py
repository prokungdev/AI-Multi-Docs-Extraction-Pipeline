from typing import Dict, List, Any
from .base import BaseOutputExporter
from .json_adapter import JsonConfigExporter
from .express_adapter import ExpressExpenseExporter

# Global Registry mapping doc_type_id -> { exporter_id -> BaseOutputExporter instance }
_REGISTRY: Dict[str, Dict[str, BaseOutputExporter]] = {
    "expense_receipt": {
        "google_sheet_summary": JsonConfigExporter(doc_type_id="expense_receipt", template_name="google_sheet_summary"),
        "accounting_line_items": JsonConfigExporter(doc_type_id="expense_receipt", template_name="accounting_line_items"),
        "express_pv": ExpressExpenseExporter(doc_type_id="expense_receipt")
    },
    "tax_invoice": {
        "google_sheet_summary": JsonConfigExporter(doc_type_id="tax_invoice", template_name="google_sheet_summary"),
        "accounting_line_items": JsonConfigExporter(doc_type_id="tax_invoice", template_name="accounting_line_items"),
        "express_pv": ExpressExpenseExporter(doc_type_id="tax_invoice")
    }
}


from src.infrastructure.common.constants import DefaultIdentifier


def register_exporter(
    exporter_id: str,
    exporter_instance: BaseOutputExporter,
    doc_type_id: str = None
):
    """Dynamically registers an exporter instance under a specific doc_type."""
    target_dt = doc_type_id or DefaultIdentifier.DOC_TYPE
    if target_dt not in _REGISTRY:
        _REGISTRY[target_dt] = {}
    _REGISTRY[target_dt][exporter_id] = exporter_instance


def get_exporter(
    doc_type_id: str = None,
    exporter_id: str = None
) -> BaseOutputExporter:
    """Retrieves the exporter instance for the given doc_type and exporter ID."""
    target_dt = doc_type_id or DefaultIdentifier.DOC_TYPE
    doc_type_exporters = _REGISTRY.get(target_dt, {})
    exporter = doc_type_exporters.get(exporter_id)
    if not exporter:
        raise ValueError(f"Exporter '{exporter_id}' not found for doc_type '{target_dt}'")
    return exporter


def list_exporters(doc_type_id: str = None) -> List[Dict[str, Any]]:
    """Lists metadata of all registered exporters for the given doc_type."""
    target_dt = doc_type_id or DefaultIdentifier.DOC_TYPE
    doc_type_exporters = _REGISTRY.get(target_dt, {})
    results = []
    for exporter_id, inst in doc_type_exporters.items():
        results.append({
            "exporter_id": exporter_id,
            "name": getattr(inst, "display_name", exporter_id.replace("_", " ").title()),
            "handler": inst,
            "has_custom_params": getattr(inst, "has_custom_params", False)
        })
    return results
