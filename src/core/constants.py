"""
Centralized System Constants for Static Infrastructure Paths and Identifiers.
All Dynamic Business Configurations MUST reside in configs/settings.json.
"""

# Static System Infrastructure Paths
DEFAULT_SETTINGS_PATH = "configs/settings.json"
DEFAULT_STORAGE_ROOT = "storage"
DEFAULT_DATABASE_FILENAME = "database/pipeline.db"
DEFAULT_LOGS_DIR = "logs"

# Fallback Identifiers (Strictly vendor and model agnostic)
DEFAULT_COMPANY_CODE = "C00000_SAMPLE"
DEFAULT_DOC_TYPE = "expense_receipt"
NO_TAX_ID = "NO_TAXID"
NO_TAX_LABEL = "no_tax"
