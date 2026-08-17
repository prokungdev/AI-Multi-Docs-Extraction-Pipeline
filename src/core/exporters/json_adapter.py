import os
from typing import List, Dict, Any
import pandas as pd
from .base import BaseOutputExporter
from src.core.transformer import transform_data

class JsonConfigExporter(BaseOutputExporter):
    """
    Adapter that wraps the existing JSON template-based data transformation.
    """
    def __init__(self, domain_id: str, template_name: str):
        super().__init__(domain_id)
        self.template_name = template_name

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
