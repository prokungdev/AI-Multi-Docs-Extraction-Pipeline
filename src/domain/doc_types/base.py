"""Base Document Type Strategy Definition.

Encapsulates prompt loading, JSON schema resolution, and document metadata
following Domain-Driven Design (DDD) principles.
"""

from abc import ABC
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from src.infrastructure.core.constants import DocTypeId, PipelineStageFolder, ProcessingType


class BaseDocType(ABC):
    """Abstract Base Class for Document Type Definitions."""

    doc_type_id: DocTypeId
    display_name: str
    description: Optional[str] = None
    processing_type: ProcessingType = ProcessingType.AI
    sort_order: int = 1
    is_active: bool = True

    # Quality and validation thresholds (Nullable for non-AI or non-financial doc types)
    confidence_high: Optional[float] = 0.85
    confidence_review: Optional[float] = 0.70
    confidence_low: Optional[float] = 0.60
    financial_tolerance: Optional[float] = 0.05

    # File naming & image processing patterns
    split_filename_pattern: str = "{doc_type}_{tax_id}_{original_filename}_{batch_id}_p{page_no}"
    archive_filename_pattern: str = "{doc_type}_{tax_id}_{doc_no}_{batch_id}_p{page_no}"
    dpi: int = 150


    def get_config_dir(self, company_code: Optional[str] = None, configs_dir: str = "configs") -> Path:
        """Resolves configuration folder path with company-specific override support."""
        if company_code and str(company_code).strip():
            company_path = Path(configs_dir) / "companies" / str(company_code).strip() / "doc_types" / self.doc_type_id.value
            if company_path.exists():
                return company_path
        return Path(configs_dir) / "doc_types" / self.doc_type_id.value

    def get_classify_prompt(self, company_code: Optional[str] = None, configs_dir: str = "configs") -> str:
        """Loads classification prompt text."""
        path = self.get_config_dir(company_code=company_code, configs_dir=configs_dir) / "classify-prompt.txt"
        if not path.exists():
            raise FileNotFoundError(f"Missing 'classify-prompt.txt' for doc_type '{self.doc_type_id.value}' at {path}")
        return path.read_text(encoding="utf-8").strip()

    def get_classify_schema(self, company_code: Optional[str] = None, configs_dir: str = "configs") -> Dict[str, Any]:
        """Loads classification JSON schema."""
        path = self.get_config_dir(company_code=company_code, configs_dir=configs_dir) / "classify-schema.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing 'classify-schema.json' for doc_type '{self.doc_type_id.value}' at {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_extract_prompt(self, company_code: Optional[str] = None, configs_dir: str = "configs") -> str:
        """Loads extraction prompt text."""
        path = self.get_config_dir(company_code=company_code, configs_dir=configs_dir) / "extract-prompt.txt"
        if not path.exists():
            raise FileNotFoundError(f"Missing 'extract-prompt.txt' for doc_type '{self.doc_type_id.value}' at {path}")
        return path.read_text(encoding="utf-8").strip()

    def get_extract_schema(self, company_code: Optional[str] = None, configs_dir: str = "configs") -> Dict[str, Any]:
        """Loads extraction JSON schema."""
        path = self.get_config_dir(company_code=company_code, configs_dir=configs_dir) / "extract-schema.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing 'extract-schema.json' for doc_type '{self.doc_type_id.value}' at {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_extract_rules(self, company_code: Optional[str] = None, configs_dir: str = "configs") -> Dict[str, Any]:
        """Loads business extraction rules."""
        path = self.get_config_dir(company_code=company_code, configs_dir=configs_dir) / "extract-rules.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing 'extract-rules.json' for doc_type '{self.doc_type_id.value}' at {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_stage_folders(self) -> List[str]:
        """Returns the canonical ordered list of pipeline stage folders for this document type.
        
        Subclasses may override this method to customize or extend specific stages.
        """
        return PipelineStageFolder.list_all()

    def to_dict(self) -> Dict[str, Any]:
        """Serializes document type definition to dictionary for UI and API serialization."""
        return {
            "doc_type_id": self.doc_type_id.value,
            "display_name": self.display_name,
            "description": self.description,
            "processing_type": self.processing_type.value if hasattr(self.processing_type, "value") else str(self.processing_type),
            "is_active": 1 if self.is_active else 0,
            "sort_order": self.sort_order,
            "confidence_high": self.confidence_high,
            "confidence_review": self.confidence_review,
            "confidence_low": self.confidence_low,
            "financial_tolerance": self.financial_tolerance,
            "split_filename_pattern": self.split_filename_pattern,
            "archive_filename_pattern": self.archive_filename_pattern,
            "dpi": self.dpi,
        }


