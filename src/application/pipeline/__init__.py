"""
Application Pipeline Orchestration Package.
Coordinates sequential document extraction stages (Stage 0 to Stage 4).
"""

from src.application.pipeline.stage_0_init import init_system  # noqa: F401
from src.application.pipeline.stage_1_ingestion import (  # noqa: F401
    split_and_match,
    release_pending_merchant_files,
)
from src.application.pipeline.stage_2_extraction import (  # noqa: F401
    extract_documents,
    async_extract_documents,
)
from src.application.pipeline.stage_3_transformation import transform_to_db  # noqa: F401
from src.application.pipeline.stage_4_validation import validate_documents  # noqa: F401
from src.application.pipeline.stage_5_confirm import confirm_receipts  # noqa: F401
from src.application.pipeline.stage_6_voucher import generate_journal_vouchers  # noqa: F401
from src.application.pipeline.stage_7_export import export_target_payloads  # noqa: F401
from src.application.pipeline.pipeline_helpers import *  # noqa: F401, F403
from src.application.pipeline.pipeline_reset import reset_pipeline_data  # noqa: F401

# Canonical Alias for Async Runner
run_ai_extraction_async = async_extract_documents

__all__ = [
    "init_system",
    "split_and_match",
    "release_pending_merchant_files",
    "extract_documents",
    "async_extract_documents",
    "run_ai_extraction_async",
    "transform_to_db",
    "validate_documents",
    "confirm_receipts",
    "generate_journal_vouchers",
    "export_target_payloads",
    "reset_pipeline_data",
]
