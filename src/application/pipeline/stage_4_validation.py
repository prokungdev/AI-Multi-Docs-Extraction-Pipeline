"""Stage 4: Validation & Post-Processing Pipeline Stage.

Coordinates rule validation, priority evaluation, auto-approval, disk archiving, and output exporters.
Delegates core validation logic to ValidatorUseCase.
"""

from src.application.usecases.validator import (
    post_process_document,
    archive_and_export_document,
    validate_batch_documents,
)


def validate_documents(
    batch_id: str,
    doc_type: str = None,
    company_code: str = None
) -> dict:
    """
    Stage 4: Validation & Post-Processing entry point.
    Delegates to validate_batch_documents usecase.
    """
    return validate_batch_documents(batch_id=batch_id, doc_type=doc_type, company_code=company_code)


__all__ = [
    "post_process_document",
    "archive_and_export_document",
    "validate_documents",
    "validate_batch_documents",
]
