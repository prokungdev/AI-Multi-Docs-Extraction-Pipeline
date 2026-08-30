"""
Stage 5: Review & Confirmation Pipeline Stage.

Coordinates document confirmation, audit stamping, and readiness validation.
Delegates core confirmation logic to ConfirmerUseCase.
"""

from typing import Dict, Any, Optional
from src.application.usecases.confirmer import (
    confirm_document,
    confirm_batch_documents,
)


def confirm_receipts(
    batch_id: str,
    company_code: Optional[str] = None,
    confirmed_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stage 5: Review & Confirm Entry Point.
    Confirms all documents belonging to the target batch.
    """
    return confirm_batch_documents(
        batch_id=batch_id,
        company_code=company_code,
        confirmed_by=confirmed_by,
    )


__all__ = [
    "confirm_document",
    "confirm_batch_documents",
    "confirm_receipts",
]
