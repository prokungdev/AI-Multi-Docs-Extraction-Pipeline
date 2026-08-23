"""
Centralized System Constants for Static Infrastructure Paths, Identifiers, and Enums.
All Dynamic Business Configurations MUST reside in configs/settings.json.
"""


class DefaultPath:
    """Static default system filesystem paths."""
    SETTINGS = "configs/settings.json"
    STORAGE_ROOT = "storage"
    DATABASE = "database/pipeline.db"
    LOGS_DIR = "logs"


class DefaultIdentifier:
    """Default fallback doc_type, company, and tax identifiers."""
    COMPANY_CODE = "C00000_SAMPLE"
    DOC_TYPE = "expense_receipt"
    NO_TAX_ID = "NO_TAXID"
    NO_TAX_LABEL = "no_tax"


class AppMetadata:
    """System application metadata."""
    NAME = "AI Multi-Docs Extraction Pipeline"
    VERSION = "1.0.0"
    DESCRIPTION = "RESTful API Backend & Pipeline Engine for Document Extraction"


class DocumentStatusCode:
    """Centralized document processing status code constants.
    Avoids magic string literals scattered across the codebase.
    Must remain in sync with document_statuses table seed data.
    """
    PENDING = "PENDING"
    PREPROCESSED = "PREPROCESSED"
    EXTRACTED = "EXTRACTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    PROCESSED = "PROCESSED"
    APPROVED = "APPROVED"
    FAILED = "FAILED"
    IGNORED = "IGNORED"


class ReviewPriority:
    """Standard document manual review priority levels."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PipelineAction:
    """Standard routing actions for classified documents."""
    PROCEED = "PROCEED"
    HOLD = "HOLD"
    IGNORE = "IGNORE"


class PipelineStageFolder:
    """Standard directory names for pipeline lifecycle stages."""
    DROP_ZONE = "01_drop_zone"
    RAW_DATA = "02_raw_data"
    PREPROCESS = "03_preprocess"
    PROCESSING = "04_processing"
    ARCHIVE = "05_archive"
    OUTPUT = "06_output"
