"""Centralized System Constants for Static Infrastructure Paths, Identifiers, and Enums.

All Dynamic Business Configurations MUST reside in configs/settings.json.
"""

import enum


class DefaultPath:
    """Static default system filesystem paths."""
    SETTINGS = "configs/settings.json"
    STORAGE_ROOT = "storage"
    DATABASE = "database/pipeline.db"
    LOGS_DIR = "logs"


class DefaultCompany:
    """Default fallback sandbox company constants."""
    CODE = "C00000_SAMPLE"
    NAME = "บริษัท ตัวอย่างทดสอบ จำกัด (สำนักงานใหญ่)"
    SHORT_NAME = "SAMPLE"
    TAX_ID = "0000000000000"
    BRANCH_CODE = "00000"


class DefaultIdentifier:
    """Default fallback doc_type, merchant, and tax identifiers."""
    COMPANY_CODE = DefaultCompany.CODE
    DOC_TYPE = "expense_receipt"
    NO_TAX_ID = "NO_TAXID"
    NO_TAX_LABEL = "no_tax"
    DEFAULT_MERCHANT_NAME = "Unknown Merchant"
    DEFAULT_SHORT_NAME = "merchant"
    UNRECOGNIZED_MERCHANT_NAME = "Unrecognized Merchant"
    AI_CONFIG_FREE = "conf_default_provider_free"
    AI_CONFIG_PAID = "conf_default_provider_paid"


class MerchantStatusCode:
    """Centralized merchant gatekeeper lifecycle status codes."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    IGNORED = "IGNORED"


class EntityIdPrefix:
    """Standardized entity Primary Key prefixes for database models and logging."""
    COMPANY = "comp"
    USER = "usr"
    ROLE = "role"
    USER_COMPANY = "uc"
    AI_CONFIG = "aic"
    BATCH = "batch"
    DOCUMENT = "doc"
    PAGE = "page"
    MERCHANT = "merch"
    RECEIPT = "rcpt"
    ITEM = "itm"
    API_LOG = "api"
    APP_LOG = "log"
    INTEGRATION_METHOD = "inm"
    TARGET_SYSTEM = "tgt"
    EXPENSE_TYPE = "ext"
    EXPENSE_ACCOUNT_MAPPING = "map"
    VOUCHER = "vch"
    VOUCHER_ITEM = "vchi"


class VatType(str, enum.Enum):
    """Universal VAT Calculation Types across accounting systems."""
    EXCLUSIVE = "EXCLUSIVE"  # แยก VAT (Express: 2)
    INCLUSIVE = "INCLUSIVE"  # รวม VAT (Express: 1)
    NO_VAT = "NO_VAT"        # ไม่มี VAT (Express: 0)


class TargetSystemId(str, enum.Enum):
    """Centralized Target System Identifiers."""
    EXPRESS = "EXPRESS"
    SAP = "SAP"
    PEAK = "PEAK"
    HR_PORTAL = "HR_PORTAL"
    GENERIC_CSV = "GENERIC_CSV"


class ConsolidateModeCode(str, enum.Enum):
    """Centralized Document Consolidation Modes."""
    BY_MERCHANT = "BY_MERCHANT"
    BY_CATEGORY = "BY_CATEGORY"
    NO_CONSOLIDATION = "NO_CONSOLIDATION"


class VoucherStatusCode(str, enum.Enum):
    """Lifecycle status codes for Journal Vouchers and RPA Export."""
    DRAFT = "DRAFT"
    READY = "READY"
    POSING = "POSING"
    POSTED = "POSTED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class SystemUserId:
    """Centralized identifiers for system actors and default development accounts."""
    SYSTEM_ADMIN = "usr_system_admin"
    AUTO_SYSTEM = "usr_system_auto"
    SYSTEM_TEST = "usr_system_test"
    DEMO = "usr_demo"


class UserRole(str, enum.Enum):
    """Standard Role-Based Access Control (RBAC) permission roles."""
    ADMIN = "ADMIN"
    REVIEWER = "REVIEWER"
    VIEWER = "VIEWER"
    SYSTEM = "SYSTEM"


class DocTypeId(str, enum.Enum):
    """Centralized Document Type Identifiers for Domain Registry and Pipeline Stages."""
    EXPENSE_RECEIPT = "expense_receipt"
    TAX_INVOICE = "tax_invoice"
    WITHHOLDING_TAX = "withholding_tax"


def generate_entity_id(prefix: str, hex_length: int = 12) -> str:
    """Generates a standardized prefixed entity identifier (e.g. doc_c4e5a5799901)."""
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:hex_length]}"


class AppMetadata:
    """System application metadata."""
    NAME = "AI Multi-Docs Extraction Pipeline"
    VERSION = "1.0.0"
    DESCRIPTION = "RESTful API Backend & Pipeline Engine for Document Extraction"


class DocumentStatusCode(str, enum.Enum):
    """Centralized document processing status code constants."""
    PENDING = "PENDING"
    PREPROCESSED = "PREPROCESSED"
    EXTRACTED = "EXTRACTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    PROCESSED = "PROCESSED"
    CONFIRMED = "CONFIRMED"
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
    STAGING = "03_staging"
    PROCESSING = "04_processing"
    ARCHIVE = "05_archive"
    OUTPUT = "06_output"

    @classmethod
    def list_all(cls) -> list[str]:
        """Returns the canonical ordered list of standard pipeline stage folder names."""
        return [
            cls.DROP_ZONE,
            cls.RAW_DATA,
            cls.PREPROCESS,
            cls.PROCESSING,
            cls.ARCHIVE,
            cls.OUTPUT,
        ]


class ProcessingType(str, enum.Enum):
    """Standard document processing strategy types."""
    AI = "AI"
    ARCHIVE_ONLY = "ARCHIVE_ONLY"


