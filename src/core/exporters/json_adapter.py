import os
from typing import List, Dict, Any
import pandas as pd
from .base import BaseOutputExporter
from src.core.transformer import transform_data, get_nested_value


class JsonConfigExporter(BaseOutputExporter):
    """
    Adapter that performs JSON template-based data transformation
    or default schema flattening for Google Sheet / Accounting summaries.
    """
    DISPLAY_NAMES = {
        "google_sheet_summary": "Google Sheet Summary (รายงานสรุปภาพรวม)",
        "accounting_line_items": "Accounting Line Items (รายงานแยกรายการสินค้า)"
    }

    def __init__(self, domain_id: str, template_name: str, display_name: str = None):
        super().__init__(domain_id)
        self.template_name = template_name
        self.display_name = display_name or self.DISPLAY_NAMES.get(template_name, template_name.replace("_", " ").title())
        self.has_custom_params = False

    def transform(self, approved_docs: List[Dict[str, Any]], **kwargs) -> pd.DataFrame:
        # Check potential template locations
        candidate_paths = [
            f"configs/doc_types/{self.domain_id}/outputs/{self.template_name}.json",
            f"configs/domains/{self.domain_id}/outputs/{self.template_name}.json",
        ]
        template_path = None
        for p in candidate_paths:
            if os.path.exists(p):
                template_path = p
                break

        all_rows = []
        for doc in approved_docs:
            data = doc.get("payload") or doc.get("data_payload") or doc
            
            if template_path:
                try:
                    rows = transform_data(data, template_path)
                    all_rows.extend(rows)
                    continue
                except Exception:
                    pass

            # Fallback Standard Transformation
            if self.template_name == "accounting_line_items":
                items = data.get("items", []) or [{}]
                for item in items:
                    all_rows.append({
                        "doc_number": get_nested_value(data, "receipt_info.receipt_number") or doc.get("doc_number", ""),
                        "doc_date": get_nested_value(data, "receipt_info.transaction_date") or doc.get("doc_date", ""),
                        "merchant_name": get_nested_value(data, "merchant.name") or doc.get("entity_name", ""),
                        "tax_id": get_nested_value(data, "merchant.tax_id") or doc.get("tax_id", ""),
                        "item_name": item.get("name", ""),
                        "quantity": item.get("quantity", item.get("qty", 1)),
                        "unit_price": item.get("unit_price", 0.0),
                        "total_price": item.get("total_price", 0.0),
                    })
            else:
                # Default: Summary Row
                all_rows.append({
                    "doc_number": get_nested_value(data, "receipt_info.receipt_number") or doc.get("doc_number", ""),
                    "doc_date": get_nested_value(data, "receipt_info.transaction_date") or doc.get("doc_date", ""),
                    "merchant_name": get_nested_value(data, "merchant.name") or doc.get("entity_name", ""),
                    "tax_id": get_nested_value(data, "merchant.tax_id") or doc.get("tax_id", ""),
                    "subtotal": get_nested_value(data, "totals.subtotal") or 0.0,
                    "vat_amount": get_nested_value(data, "totals.vat_amount") or 0.0,
                    "net_amount": get_nested_value(data, "totals.net_amount") or 0.0,
                })

        return pd.DataFrame(all_rows)
