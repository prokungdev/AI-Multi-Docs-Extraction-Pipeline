"""Storage Path Manager and Directory Resolver (External Layer)."""

import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.infrastructure.core.logger import logger

from src.infrastructure.core.config import load_system_settings
from src.infrastructure.core.constants import (
    DefaultPath,
    DefaultIdentifier,
    PipelineStageFolder,
)
from .local_adapter import LocalStorageAdapter


class StoragePathManager:
    """
    Centralized Single Source of Truth for all filesystem storage paths.
    Provides standard path resolution and atomic safe file operations across the entire pipeline.
    """

    def __init__(self, settings_path: str = DefaultPath.SETTINGS):
        self.settings_path = settings_path
        self._settings = load_system_settings(settings_path)
        self.storage_root = os.environ.get("STORAGE_ROOT_OVERRIDE") or self._settings.get("storage_root", DefaultPath.STORAGE_ROOT)
        self.default_company = DefaultIdentifier.COMPANY_CODE
        self.default_doc_type = DefaultIdentifier.DOC_TYPE
        self.adapter = LocalStorageAdapter()

    @property
    def root(self) -> str:
        """Returns normalized root storage path, dynamically evaluating environment overrides."""
        override = os.environ.get("STORAGE_ROOT_OVERRIDE")
        if override and override.strip():
            return override.strip().replace("\\", "/")
        return (self.storage_root or DefaultPath.STORAGE_ROOT).replace("\\", "/")

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

    def get_stage_dir(self, stage_folder_name: str, company_code: Optional[str] = None, doc_type: Optional[str] = None, *subpaths: str) -> str:
        """Constructs full path for any standard pipeline stage folder."""
        dt_root = self.get_doc_type_root(company_code, doc_type)
        path = os.path.join(dt_root, stage_folder_name, *subpaths).replace("\\", "/")
        os.makedirs(path, exist_ok=True)
        return path

    def get_drop_zone_dir(self, company_code: Optional[str] = None, doc_type: Optional[str] = None, source_channel: str = "Upload") -> str:
        """01_drop_zone/{source_channel}"""
        return self.get_stage_dir(PipelineStageFolder.DROP_ZONE, company_code, doc_type, source_channel)

    def get_raw_data_dir(self, company_code: Optional[str] = None, doc_type: Optional[str] = None, status: Optional[str] = None, merchant_folder: Optional[str] = None) -> str:
        """02_raw_data/[status]/[merchant_folder]"""
        subpaths = []
        if status:
            subpaths.append(status)
        if merchant_folder:
            subpaths.append(merchant_folder)
        return self.get_stage_dir(PipelineStageFolder.RAW_DATA, company_code, doc_type, *subpaths)

    def get_staging_dir(self, company_code: Optional[str] = None, doc_type: Optional[str] = None, status: Optional[str] = None, merchant_folder: Optional[str] = None) -> str:
        """03_staging/[status]/[merchant_folder]"""
        subpaths = []
        if status:
            subpaths.append(status)
        if merchant_folder:
            subpaths.append(merchant_folder)
        return self.get_stage_dir(PipelineStageFolder.STAGING, company_code, doc_type, *subpaths)

    def get_processing_dir(self, company_code: Optional[str] = None, doc_type: Optional[str] = None, merchant_folder: Optional[str] = None) -> str:
        """04_processing/[merchant_folder]"""
        subpaths = [merchant_folder] if merchant_folder else []
        return self.get_stage_dir(PipelineStageFolder.PROCESSING, company_code, doc_type, *subpaths)

    def get_preprocess_dir(self, company_code: Optional[str] = None, doc_type: Optional[str] = None, merchant_folder: Optional[str] = None) -> str:
        """Alias for get_processing_dir."""
        return self.get_processing_dir(company_code, doc_type, merchant_folder)

    def get_archive_dir(self, company_code: Optional[str] = None, doc_type: Optional[str] = None, year_month: Optional[str] = None, sub: Optional[str] = None) -> str:
        """05_archive/[YYYY-MM]/[raw|verified_json]"""
        subpaths = []
        if year_month:
            subpaths.append(year_month)
        if sub:
            subpaths.append(sub)
        return self.get_stage_dir(PipelineStageFolder.ARCHIVE, company_code, doc_type, *subpaths)

    def get_output_dir(self, company_code: Optional[str] = None, doc_type: Optional[str] = None, subfolder: Optional[str] = None) -> str:
        """06_output/[subfolder]"""
        subpaths = [subfolder] if subfolder else []
        return self.get_stage_dir(PipelineStageFolder.OUTPUT, company_code, doc_type, *subpaths)

    def cleanup_empty_staging_folders(self, company_code: Optional[str] = None, doc_type: Optional[str] = None) -> int:
        """Cleans up empty staging and raw_data merchant directories."""
        deleted_count = 0
        for stage in [PipelineStageFolder.RAW_DATA, PipelineStageFolder.STAGING]:
            target_root = self.get_stage_dir(stage, company_code, doc_type)
            if not os.path.exists(target_root):
                continue
            for status_dir in os.listdir(target_root):
                status_path = os.path.join(target_root, status_dir)
                if not os.path.isdir(status_path):
                    continue
                for merchant_dir in os.listdir(status_path):
                    merchant_path = os.path.join(status_path, merchant_dir)
                    if os.path.isdir(merchant_path):
                        try:
                            if not os.listdir(merchant_path):
                                os.rmdir(merchant_path)
                                deleted_count += 1
                                logger.debug(f"Removed empty subfolder: {merchant_path}")
                        except Exception as e:
                            logger.warning(f"Could not remove folder '{merchant_path}': {e}")
        return deleted_count



storage_manager = StoragePathManager()

