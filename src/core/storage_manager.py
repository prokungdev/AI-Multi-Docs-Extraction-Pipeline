import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.core.logger import logger

from src.core.config_loader import load_system_settings
from src.core.constants import (
    DefaultPath,
    DefaultIdentifier,
    PipelineStageFolder,
)


class StoragePathManager:
    """
    Centralized Single Source of Truth for all filesystem storage paths.
    Provides standard path resolution and atomic safe file operations across the entire pipeline.
    """

    def __init__(self, settings_path: str = DefaultPath.SETTINGS):
        self.settings_path = settings_path
        self._settings = load_system_settings(settings_path)
        self.storage_root = self._settings.get("storage_root", DefaultPath.STORAGE_ROOT)
        self.default_company = DefaultIdentifier.COMPANY_CODE
        self.default_doc_type = DefaultIdentifier.DOC_TYPE

    @property
    def root(self) -> str:
        """Returns normalized root storage path."""
        return self.storage_root.replace("\\", "/")

    def get_database_dir(self) -> str:
        """Returns the central SQLite database directory (storage/database)."""
        path = os.path.join(self.root, "database").replace("\\", "/")
        os.makedirs(path, exist_ok=True)
        return path

    def get_database_path(self, filename: str = "pipeline.db") -> str:
        """Returns the full path to the centralized database file."""
        return os.path.join(self.get_database_dir(), filename).replace("\\", "/")

    def get_company_root(self, company_code: Optional[str] = None) -> str:
        """Returns root folder for a given company: storage/companies/{company_code}."""
        comp = (company_code or self.default_company).strip().upper()
        path = os.path.join(self.root, "companies", comp).replace("\\", "/")
        os.makedirs(path, exist_ok=True)
        return path

    def get_doc_type_root(self, company_code: Optional[str] = None, doc_type: Optional[str] = None) -> str:
        """Returns root folder for a company's doc_type: storage/companies/{comp}/{doc_type}."""
        comp_root = self.get_company_root(company_code)
        dt = (doc_type or self.default_doc_type).strip().lower()
        path = os.path.join(comp_root, dt).replace("\\", "/")
        os.makedirs(path, exist_ok=True)
        return path

    def get_stage_dir(
        self,
        stage_name: str,
        company_code: Optional[str] = None,
        doc_type: Optional[str] = None
    ) -> str:
        """
        Returns a stage directory for a company doc_type.
        Example: storage/companies/C00000_SAMPLE/expense_receipt/01_drop_zone
        """
        dt_root = self.get_doc_type_root(company_code, doc_type)
        path = os.path.join(dt_root, stage_name).replace("\\", "/")
        os.makedirs(path, exist_ok=True)
        return path

    def get_drop_zone_dir(
        self,
        company_code: Optional[str] = None,
        doc_type: Optional[str] = None,
        sub_folder: Optional[str] = None
    ) -> str:
        """Returns drop zone directory or specific drop subfolder (e.g. Upload, Auto_Scanner)."""
        base = self.get_stage_dir(PipelineStageFolder.DROP_ZONE, company_code, doc_type)
        if sub_folder:
            path = os.path.join(base, sub_folder).replace("\\", "/")
            os.makedirs(path, exist_ok=True)
            return path
        return base

    def get_raw_data_dir(
        self,
        company_code: Optional[str] = None,
        doc_type: Optional[str] = None,
        status: Optional[str] = None,
        merchant_folder: Optional[str] = None
    ) -> str:
        """
        Returns raw data routing directory.
        - None: storage/companies/{c}/{dt}/02_raw_data
        - status='PENDING', merchant_folder='0107542000011_cpall': .../02_raw_data/PENDING/0107542000011_cpall
        """
        base = self.get_stage_dir(PipelineStageFolder.RAW_DATA, company_code, doc_type)
        if status:
            base = os.path.join(base, status.upper()).replace("\\", "/")
        if merchant_folder:
            base = os.path.join(base, merchant_folder).replace("\\", "/")
        os.makedirs(base, exist_ok=True)
        return base

    def get_preprocess_dir(self, company_code: Optional[str] = None, doc_type: Optional[str] = None) -> str:
        """Returns preprocess directory: storage/companies/{c}/{dt}/03_preprocess."""
        return self.get_stage_dir(PipelineStageFolder.PREPROCESS, company_code, doc_type)

    def get_processing_dir(self, company_code: Optional[str] = None, doc_type: Optional[str] = None) -> str:
        """Returns processing queue directory: storage/companies/{c}/{dt}/04_processing."""
        return self.get_stage_dir(PipelineStageFolder.PROCESSING, company_code, doc_type)

    def get_extracted_dir(self, company_code: Optional[str] = None, doc_type: Optional[str] = None) -> str:
        """Alias for get_processing_dir for extracted JSON payloads."""
        return self.get_processing_dir(company_code, doc_type)

    def get_archive_dir(
        self,
        company_code: Optional[str] = None,
        doc_type: Optional[str] = None,
        year_month: Optional[str] = None,
        sub: Optional[str] = "raw"
    ) -> str:
        """
        Returns archive directory with optional YYYY-MM subpartitioning.
        Example: storage/companies/C00000_SAMPLE/expense_receipt/05_archive/2026-08/raw
        """
        base = self.get_stage_dir(PipelineStageFolder.ARCHIVE, company_code, doc_type)
        if year_month:
            base = os.path.join(base, year_month).replace("\\", "/")
        if sub:
            base = os.path.join(base, sub).replace("\\", "/")
        os.makedirs(base, exist_ok=True)
        return base

    def get_output_dir(self, company_code: Optional[str] = None, doc_type: Optional[str] = None) -> str:
        """Returns final export output directory: storage/companies/{c}/{dt}/06_output."""
        return self.get_stage_dir(PipelineStageFolder.OUTPUT, company_code, doc_type)

    @staticmethod
    def safe_move_file(source_path: str, target_dir: str, overwrite: bool = True) -> str:
        """
        Safely moves a file to target directory with error checking and directory creation.
        Returns the destination file path.
        """
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source file not found for move: {source_path}")

        os.makedirs(target_dir, exist_ok=True)
        filename = os.path.basename(source_path)
        dest_path = os.path.join(target_dir, filename).replace("\\", "/")

        if os.path.exists(dest_path) and not overwrite:
            stem, ext = os.path.splitext(filename)
            import uuid
            dest_path = os.path.join(target_dir, f"{stem}_{uuid.uuid4().hex[:6]}{ext}").replace("\\", "/")

        shutil.move(source_path, dest_path)
        return dest_path


# Global singleton instance for easy import across modules
storage_manager = StoragePathManager()
