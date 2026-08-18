import os
from typing import List, Dict, Any
import pandas as pd
from .base import BaseOutputExporter
from src.core.transformer import transform_data

class JsonConfigExporter(BaseOutputExporter):
    """
    Adapter that wraps the existing JSON template-based data transformation.
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
        template_path = f"configs/domains/{self.domain_id}/outputs/{self.template_name}.json"
        
        all_rows = []
        for doc in approved_docs:
            try:
                # Call original transformer logic
                rows = transform_data(doc, template_path)
                all_rows.extend(rows)
            except Exception as e:
                # Gracefully skip if a document cannot be transformed
                pass
                
        return pd.DataFrame(all_rows)
