import os
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import pandas as pd
from loguru import logger


class BaseOutputExporter(ABC):
    """
    Abstract Strategy Interface for all document output exporters.
    Handles data transformations and standard file export (CSV, JSON, Excel).
    """
    display_name: str = ""
    has_custom_params: bool = False
    encoding: str = "utf-8-sig"
    delimiter: str = ","

    def __init__(self, domain_id: str):
        self.domain_id = domain_id
        if not self.display_name:
            self.display_name = self.__class__.__name__

    @abstractmethod
    def transform(self, approved_docs: List[Dict[str, Any]], **kwargs) -> pd.DataFrame:
        """
        Transforms approved documents into a flattened pandas DataFrame.
        Must be implemented by concrete subclasses.
        """
        pass

    def export(
        self,
        approved_docs: List[Dict[str, Any]],
        output_file_base: str,
        export_csv: bool = True,
        export_json: bool = True,
        **kwargs
    ) -> Dict[str, str]:
        """
        Executes the transformation and writes/appends outputs to CSV and/or JSON.
        Returns a dictionary of generated file paths.
        """
        df_new = self.transform(approved_docs, **kwargs)
        if df_new.empty:
            logger.info(f"Exporter '{self.display_name}' produced 0 rows. Skipping file write.")
            return {}

        results = {}
        out_dir = os.path.dirname(output_file_base)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # 1. Export CSV
        if export_csv:
            csv_path = f"{output_file_base}.csv"
            if os.path.exists(csv_path):
                try:
                    df_old = pd.read_csv(csv_path, encoding=self.encoding, sep=self.delimiter)
                    df_final = pd.concat([df_old, df_new], ignore_index=True)
                except Exception:
                    df_final = df_new
            else:
                df_final = df_new

            df_final.to_csv(csv_path, index=False, encoding=self.encoding, sep=self.delimiter)
            results["csv"] = csv_path

        # 2. Export JSON
        if export_json:
            json_path = f"{output_file_base}.json"
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as rf:
                        list_old = json.load(rf)
                except Exception:
                    list_old = []
            else:
                list_old = []

            list_old.extend(df_new.to_dict(orient="records"))
            with open(json_path, "w", encoding="utf-8") as wf:
                json.dump(list_old, wf, ensure_ascii=False, indent=2)
            results["json"] = json_path

        logger.info(f"Exported {len(df_new)} record(s) using '{self.display_name}' -> {list(results.values())}")
        return results

    def export_to_csv(self, df: pd.DataFrame, output_path: str, encoding: str = None, delimiter: str = None):
        """Exports a DataFrame to a standalone CSV file."""
        enc = encoding or self.encoding
        sep = delimiter or self.delimiter
        df.to_csv(output_path, index=False, encoding=enc, sep=sep)

    def export_to_excel(self, df: pd.DataFrame, output_path: str):
        """Exports a DataFrame to an Excel spreadsheet."""
        df.to_excel(output_path, index=False, engine="openpyxl")
