from abc import ABC, abstractmethod
from typing import List, Dict, Any
import pandas as pd

class BaseOutputExporter(ABC):
    """
    Abstract base class for all domain output exporters.
    Handles data transformations and common file exports.
    """
    def __init__(self, domain_id: str):
        self.domain_id = domain_id

    @abstractmethod
    def transform(self, approved_docs: List[Dict[str, Any]], **kwargs) -> pd.DataFrame:
        """
        Transforms approved documents into a flattened pandas DataFrame.
        Must be implemented by subclasses.
        """
        pass

    def export_to_csv(self, df: pd.DataFrame, output_path: str, encoding: str = "utf-8-sig", delimiter: str = ","):
        """
        Exports a DataFrame to a CSV file.
        """
        df.to_csv(output_path, index=False, encoding=encoding, sep=delimiter)

    def export_to_excel(self, df: pd.DataFrame, output_path: str):
        """
        Exports a DataFrame to an Excel spreadsheet.
        """
        df.to_excel(output_path, index=False, engine="openpyxl")
