from typing import Dict, List, Any
from .base import BaseOutputExporter
from .json_adapter import JsonConfigExporter
from .express_adapter import ExpressExpenseExporter

# Global Registry mapping domain_id -> { exporter_id -> BaseOutputExporter instance }
_REGISTRY: Dict[str, Dict[str, BaseOutputExporter]] = {
    "expense_receipt": {
        "google_sheet_summary": JsonConfigExporter(domain_id="expense_receipt", template_name="google_sheet_summary"),
        "accounting_line_items": JsonConfigExporter(domain_id="expense_receipt", template_name="accounting_line_items"),
        "express_pv": ExpressExpenseExporter(domain_id="expense_receipt")
    },
    "tax_invoice": {
        "google_sheet_summary": JsonConfigExporter(domain_id="tax_invoice", template_name="google_sheet_summary"),
        "accounting_line_items": JsonConfigExporter(domain_id="tax_invoice", template_name="accounting_line_items"),
        "express_pv": ExpressExpenseExporter(domain_id="tax_invoice")
    }
}


def register_exporter(domain_id: str, exporter_id: str, exporter_instance: BaseOutputExporter):
    """Dynamically registers an exporter instance under a specific domain."""
    if domain_id not in _REGISTRY:
        _REGISTRY[domain_id] = {}
    _REGISTRY[domain_id][exporter_id] = exporter_instance


def get_exporter(domain_id: str, exporter_id: str) -> BaseOutputExporter:
    """Retrieves the exporter instance for the given domain and exporter ID."""
    domain_exporters = _REGISTRY.get(domain_id, {})
    exporter = domain_exporters.get(exporter_id)
    if not exporter:
        raise ValueError(f"Exporter '{exporter_id}' not found for domain '{domain_id}'")
    return exporter


def list_exporters(domain_id: str) -> List[Dict[str, Any]]:
    """Lists metadata of all registered exporters for the given domain."""
    domain_exporters = _REGISTRY.get(domain_id, {})
    results = []
    for exporter_id, inst in domain_exporters.items():
        results.append({
            "exporter_id": exporter_id,
            "name": getattr(inst, "display_name", exporter_id.replace("_", " ").title()),
            "handler": inst,
            "has_custom_params": getattr(inst, "has_custom_params", False)
        })
    return results


# Alias for backward compatibility
get_domain_exporters = list_exporters
