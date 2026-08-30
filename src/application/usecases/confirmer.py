"""
Application Use Case: Document Review & Confirmation.
Validates document lifecycle state, stamps actor confirmation, and prepares documents for Journal Voucher Generation.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy import select, and_

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import (
    DocumentStatusCode,
    SystemUserId,
)
from src.infrastructure.core.user_context import get_current_user_id
from src.infrastructure.database.engine import get_db_session
from src.infrastructure.database.models import DocumentControl, Company


def confirm_document(
    document_id: str,
    confirmed_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Confirms an individual document control record after review.
    Sets status to CONFIRMED (or APPROVED), stamps confirmed_by and confirmed_at.
    """
    if not document_id or not str(document_id).strip():
        raise ValueError("document_id is required for confirmation (Fail-Fast).")

    clean_doc_id = str(document_id).strip()
    actor = confirmed_by or get_current_user_id() or SystemUserId.SYSTEM_ADMIN
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_session() as session:
        doc = session.scalars(
            select(DocumentControl).filter_by(document_id=clean_doc_id)
        ).first()

        if not doc:
            raise KeyError(f"DocumentControl '{clean_doc_id}' not found in database.")

        if doc.is_closed == 1:
            raise RuntimeError(f"DocumentControl '{clean_doc_id}' is sealed/closed and cannot be re-confirmed.")

        doc.status_code = DocumentStatusCode.CONFIRMED.value
        doc.confirmed_by = actor
        doc.confirmed_at = now_iso
        doc.updated_by = actor
        doc.updated_at = now_iso

        session.commit()
        logger.info(f"Document '{clean_doc_id}' successfully confirmed by actor '{actor}'.")
        return {
            "document_id": clean_doc_id,
            "status": DocumentStatusCode.CONFIRMED.value,
            "confirmed_by": actor,
            "confirmed_at": now_iso,
        }


def confirm_batch_documents(
    batch_id: str,
    company_code: Optional[str] = None,
    confirmed_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Confirms all open/processed documents in a specific batch.
    """
    if not batch_id or not str(batch_id).strip():
        raise ValueError("batch_id is required for batch confirmation (Fail-Fast).")

    clean_batch_id = str(batch_id).strip()
    actor = confirmed_by or get_current_user_id() or SystemUserId.SYSTEM_ADMIN
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_session() as session:
        stmt = select(DocumentControl).where(
            and_(
                DocumentControl.batch_id == clean_batch_id,
                DocumentControl.is_closed == 0,
            )
        )

        if company_code:
            comp = session.scalars(select(Company).filter_by(company_code=company_code)).first()
            if comp:
                stmt = stmt.where(DocumentControl.company_id == comp.company_id)

        docs = session.scalars(stmt).all()
        confirmed_count = 0

        for doc in docs:
            doc.status_code = DocumentStatusCode.CONFIRMED.value
            doc.confirmed_by = actor
            doc.confirmed_at = now_iso
            doc.updated_by = actor
            doc.updated_at = now_iso
            confirmed_count += 1

        session.commit()
        logger.info(f"Batch '{clean_batch_id}': Confirmed {confirmed_count} document(s) by '{actor}'.")

        return {
            "batch_id": clean_batch_id,
            "confirmed_count": confirmed_count,
            "confirmed_by": actor,
            "confirmed_at": now_iso,
        }
