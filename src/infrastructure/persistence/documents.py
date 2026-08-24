"""Document and batch database operations using Pure SQLAlchemy 2.0 ORM."""

import os
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple
from src.infrastructure.common.logger import logger
from sqlalchemy import select, update, delete, or_, and_, desc, asc, func

from .connection import get_db_session
from .models import Company, ProcessedBatch, DocumentPage, Document, DocumentStatus
from src.infrastructure.common.constants import DefaultIdentifier, DocumentStatusCode, SystemUserId

DEFAULT_LOCK_TTL_SECONDS = 900  # 15 minutes Airline Ticket Hold duration


def calculate_file_hash(file_path: str) -> str:
    """Returns SHA-256 hex digest of file contents."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def check_duplicate_document(file_hash: str, company_id: str = None) -> tuple[bool, dict | None]:
    """Checks if a batch with the given SHA-256 hash already exists."""
    try:
        with get_db_session() as session:
            stmt = select(ProcessedBatch).filter_by(file_hash=file_hash)
            if company_id:
                stmt = stmt.where(ProcessedBatch.company_id == company_id)
            batch = session.scalars(stmt).first()
            if batch:
                first_doc = session.scalars(select(Document).filter_by(batch_id=batch.batch_id)).first()
                metadata = {
                    "batch_id": batch.batch_id,
                    "company_id": batch.company_id,
                    "original_filename": batch.original_filename,
                    "original_pdf_name": batch.original_filename,
                    "created_at": batch.created_at,
                    "status": first_doc.status_code if first_doc else DocumentStatusCode.PENDING,
                    "doc_type_id": first_doc.domain_id if first_doc else DefaultIdentifier.DOC_TYPE,
                    "source": first_doc.source_id if first_doc else DefaultIdentifier.NO_TAX_LABEL
                }
                return True, metadata
    except Exception as e:
        logger.error(f"Error checking duplicate document hash: {e}")
    return False, None


def create_batch(batch_id: str, original_filename: str = None, total_pages: int = 1,
                 storage_path: str = "", file_hash: str = "", original_pdf_name: str = None,
                 company_id: str = None) -> bool:
    """Inserts or updates a batch record using Pure SQLAlchemy 2.0 ORM."""
    filename = original_filename or original_pdf_name or "document.pdf"
    try:
        with get_db_session() as session:
            target_cid = company_id
            if not target_cid:
                def_comp = session.scalars(select(Company).filter_by(company_code=DefaultIdentifier.COMPANY_CODE)).first()
                if def_comp:
                    target_cid = def_comp.company_id

            created_at = datetime.now(timezone.utc).isoformat()
            batch = session.scalars(select(ProcessedBatch).filter_by(batch_id=batch_id)).first()
            if batch:
                if target_cid:
                    batch.company_id = target_cid
                batch.original_filename = filename
                batch.total_pages = total_pages
                batch.storage_path = storage_path
                batch.file_hash = file_hash
            else:
                batch = ProcessedBatch(
                    batch_id=batch_id,
                    company_id=target_cid,
                    original_filename=filename,
                    total_pages=total_pages,
                    storage_path=storage_path,
                    file_hash=file_hash,
                    created_at=created_at
                )
                session.add(batch)
            return True
    except Exception as e:
        logger.error(f"Failed to create batch '{batch_id}': {e}")
        return False


def create_page(page_id: str, batch_id: str, page_number: int, image_path: str, status_code: str, error_reason: str = None) -> bool:
    """
    Inserts or updates a page record using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            created_at = datetime.now(timezone.utc).isoformat()
            page = session.scalars(select(DocumentPage).filter_by(page_id=page_id)).first()
            if page:
                page.batch_id = batch_id
                page.page_number = page_number
                page.image_path = image_path
                page.status_code = status_code
                page.error_reason = error_reason
            else:
                page = DocumentPage(
                    page_id=page_id,
                    batch_id=batch_id,
                    page_number=page_number,
                    image_path=image_path,
                    status_code=status_code,
                    error_reason=error_reason,
                    created_at=created_at
                )
                session.add(page)
            return True
    except Exception as e:
        logger.error(f"Failed to create page '{page_id}': {e}")
        return False


def update_page(page_id: str, image_path: str = None, status_code: str = None, error_reason: str = None) -> bool:
    """
    Updates an existing page record using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            page = session.scalars(select(DocumentPage).filter_by(page_id=page_id)).first()
            if not page:
                return False
            if image_path is not None:
                page.image_path = image_path
            if status_code is not None:
                page.status_code = status_code
            if error_reason is not None:
                page.error_reason = error_reason
            return True
    except Exception as e:
        logger.error(f"Failed to update page '{page_id}': {e}")
        return False


def update_page_status(page_id: str, status_code: str, error_reason: str = None) -> bool:
    """
    Convenience helper to update status and error reason of a page.
    """
    return update_page(page_id, status_code=status_code, error_reason=error_reason)


def update_pages_status_batch(updates: List[Tuple[str, str | None, str, int]]) -> bool:
    """
    Batch update page statuses using Pure SQLAlchemy 2.0 ORM.
    Args:
        updates: List of tuples (status_code, error_reason, batch_id, page_number)
    """
    try:
        with get_db_session() as session:
            for status_code, error_reason, batch_id, page_number in updates:
                stmt = select(DocumentPage).filter_by(batch_id=batch_id, page_number=page_number)
                page = session.scalars(stmt).first()
                if page:
                    page.status_code = status_code
                    page.error_reason = error_reason
            return True
    except Exception as e:
        logger.error(f"Failed to batch update page statuses: {e}")
        return False


def create_document(
    document_id: str,
    batch_id: str,
    doc_type_id: str = None,
    domain_id: str = None,
    source_id: str = DefaultIdentifier.NO_TAX_ID,
    status_code: str = DocumentStatusCode.PROCESSED,
    doc_number: str = None,
    doc_date: str = None,
    entity_name: str = None,
    total_amount: float = None,
    search_text: str = None,
    data_payload: str = None,
    error_reason: str = None,
    model_used: str = None,
    input_tokens: int = None,
    output_tokens: int = None,
    cost_usd: float = 0.0,
    cost_thb: float = 0.0,
    is_free_tier: int = 0,
    overall_confidence: float = None,
    confidence_level: str = None,
    is_blurry: int = None,
    is_ambiguous: int = None,
    has_ambiguous_fields: int = None,
    confidence_notes: str = None,
    review_priority: str = None,
    is_auto_approved: int = None,
    auto_approved: int = None,
    company_id: str = None
) -> bool:
    """
    Inserts or updates a document record using Pure SQLAlchemy 2.0 ORM.
    """
    final_dt = doc_type_id or domain_id or DefaultIdentifier.DOC_TYPE
    final_auto_approved = is_auto_approved if is_auto_approved is not None else (auto_approved or 0)
    final_ambiguous = is_ambiguous if is_ambiguous is not None else (has_ambiguous_fields or 0)

    try:
        with get_db_session() as session:
            target_cid = company_id
            if not target_cid:
                batch_obj = session.scalars(select(ProcessedBatch).filter_by(batch_id=batch_id)).first()
                if batch_obj and batch_obj.company_id:
                    target_cid = batch_obj.company_id
                else:
                    def_comp = session.scalars(select(Company).filter_by(company_code=DefaultIdentifier.COMPANY_CODE)).first()
                    if def_comp:
                        target_cid = def_comp.company_id

            created_at = datetime.now(timezone.utc).isoformat()
            doc = session.scalars(select(Document).filter_by(document_id=document_id)).first()
            if doc:
                if target_cid:
                    doc.company_id = target_cid
                doc.batch_id = batch_id
                doc.domain_id = final_dt
                doc.source_id = source_id
                doc.status_code = status_code
                doc.doc_number = doc_number
                doc.doc_date = doc_date
                doc.entity_name = entity_name
                doc.total_amount = total_amount
                doc.search_text = search_text
                doc.data_payload = data_payload
                doc.error_reason = error_reason
                doc.model_used = model_used
                doc.input_tokens = input_tokens or 0
                doc.output_tokens = output_tokens or 0
                doc.cost_usd = cost_usd or 0.0
                doc.cost_thb = cost_thb or 0.0
                doc.is_free_tier = is_free_tier or 0
                doc.overall_confidence = overall_confidence
                doc.confidence_level = confidence_level
                doc.is_blurry = is_blurry
                doc.is_ambiguous = final_ambiguous
                doc.confidence_notes = confidence_notes
                doc.review_priority = review_priority
                doc.is_auto_approved = final_auto_approved
                doc.updated_at = created_at
            else:
                doc = Document(
                    document_id=document_id,
                    company_id=target_cid,
                    batch_id=batch_id,
                    domain_id=final_dt,
                    source_id=source_id,
                    status_code=status_code,
                    doc_number=doc_number,
                    doc_date=doc_date,
                    entity_name=entity_name,
                    total_amount=total_amount,
                    search_text=search_text,
                    data_payload=data_payload,
                    error_reason=error_reason,
                    model_used=model_used,
                    input_tokens=input_tokens or 0,
                    output_tokens=output_tokens or 0,
                    cost_usd=cost_usd or 0.0,
                    cost_thb=cost_thb or 0.0,
                    is_free_tier=is_free_tier or 0,
                    overall_confidence=overall_confidence,
                    confidence_level=confidence_level,
                    is_blurry=is_blurry,
                    is_ambiguous=final_ambiguous,
                    confidence_notes=confidence_notes,
                    review_priority=review_priority,
                    is_auto_approved=final_auto_approved,
                    created_at=created_at
                )
                session.add(doc)
            return True
    except Exception as e:
        logger.error(f"Failed to create document '{document_id}': {e}")
        return False


def link_pages_to_document(document_id: str, page_ids: list[str]) -> bool:
    """
    Links given page_ids to a document_id using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            for pid in page_ids:
                page = session.scalars(select(DocumentPage).filter_by(page_id=pid)).first()
                if page:
                    page.document_id = document_id
            return True
    except Exception as e:
        logger.error(f"Failed to link pages to document '{document_id}': {e}")
        return False


def get_document_by_id(document_id: str) -> dict | None:
    """
    Retrieves full document record joined with batch info using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            doc = session.scalars(select(Document).filter_by(document_id=document_id)).first()
            if not doc:
                return None
            doc_dict = doc.to_dict()
            batch = session.scalars(select(ProcessedBatch).filter_by(batch_id=doc.batch_id)).first()
            if batch:
                doc_dict["original_filename"] = batch.original_filename
                doc_dict["original_pdf_name"] = batch.original_filename
                doc_dict["storage_path"] = batch.storage_path
            return doc_dict
    except Exception as e:
        logger.error(f"Failed to get document '{document_id}': {e}")
        return None


def get_document_pages(document_id: str) -> list[dict]:
    """
    Retrieves all pages associated with a specific document using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            stmt = select(DocumentPage).filter_by(document_id=document_id).order_by(DocumentPage.page_number.asc())
            pages = session.scalars(stmt).all()
            return [p.to_dict() for p in pages]
    except Exception as e:
        logger.error(f"Failed to get pages for document '{document_id}': {e}")
        return []


def get_batch_pages(batch_id: str) -> list[dict]:
    """
    Retrieves all pages belonging to a batch using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            stmt = select(DocumentPage).filter_by(batch_id=batch_id).order_by(DocumentPage.page_number.asc())
            pages = session.scalars(stmt).all()
            return [p.to_dict() for p in pages]
    except Exception as e:
        logger.error(f"Failed to get pages for batch '{batch_id}': {e}")
        return []


def get_pending_documents(domain_id: str = None, source_id: str = None, company_id: str = None) -> list[dict]:
    """
    Retrieves documents waiting for review using Pure SQLAlchemy 2.0 ORM.
    Optionally filters by company_id.
    """
    try:
        with get_db_session() as session:
            stmt = select(Document, ProcessedBatch).join(
                ProcessedBatch, Document.batch_id == ProcessedBatch.batch_id
            ).where(
                Document.status_code.in_([
                    DocumentStatusCode.PENDING,
                    DocumentStatusCode.NEEDS_REVIEW,
                    DocumentStatusCode.PROCESSED,
                ])
            )

            if company_id:
                stmt = stmt.where(Document.company_id == company_id)
            if domain_id:
                stmt = stmt.where(Document.domain_id == domain_id)
            if source_id:
                stmt = stmt.where(Document.source_id == source_id)

            stmt = stmt.order_by(
                Document.review_priority.desc(),
                Document.created_at.desc()
            )

            results = session.execute(stmt).all()
            docs = []
            for doc, batch in results:
                d = doc.to_dict()
                d["original_filename"] = batch.original_filename
                d["original_pdf_name"] = batch.original_filename
                d["storage_path"] = batch.storage_path
                docs.append(d)
            return docs
    except Exception as e:
        logger.error(f"Failed to get pending documents: {e}")
        return []


def get_all_documents(domain_id: str = None, source_id: str = None, status_code: str = None, company_id: str = None) -> list[dict]:
    """
    Retrieves all documents matching criteria using Pure SQLAlchemy 2.0 ORM.
    Optionally filters by company_id.
    """
    try:
        with get_db_session() as session:
            stmt = select(Document, ProcessedBatch).join(
                ProcessedBatch, Document.batch_id == ProcessedBatch.batch_id
            )

            if company_id:
                stmt = stmt.where(Document.company_id == company_id)
            if domain_id:
                stmt = stmt.where(Document.domain_id == domain_id)
            if source_id:
                stmt = stmt.where(Document.source_id == source_id)
            if status_code:
                stmt = stmt.where(Document.status_code == status_code)

            stmt = stmt.order_by(Document.created_at.desc())
            results = session.execute(stmt).all()
            docs = []
            for doc, batch in results:
                d = doc.to_dict()
                d["original_filename"] = batch.original_filename
                d["original_pdf_name"] = batch.original_filename
                d["storage_path"] = batch.storage_path
                docs.append(d)
            return docs
    except Exception as e:
        logger.error(f"Failed to get all documents: {e}")
        return []


def update_document_to_approved(
    document_id: str,
    confirmed_by: str = SystemUserId.DEV_ADMIN,
    doc_number: str = None,
    doc_date: str = None,
    entity_name: str = None,
    total_amount: float = None,
    data_payload: str = None,
    is_manually_edited: int = 0
) -> bool:
    """
    Marks a document as APPROVED and closes it using Atomic Guard (is_closed == 0).
    """
    try:
        with get_db_session() as session:
            doc = session.scalars(
                select(Document).where(Document.document_id == document_id, Document.is_closed == 0)
            ).first()
            if not doc:
                logger.warning(f"Cannot approve document '{document_id}': Document does not exist or is already closed.")
                return False
            now_str = datetime.now(timezone.utc).isoformat()
            doc.status_code = DocumentStatusCode.APPROVED
            doc.is_closed = 1
            doc.is_locked = 0
            doc.locked_by = None
            doc.locked_at = None
            doc.confirmed_by = confirmed_by
            doc.confirmed_at = now_str
            doc.is_manually_edited = is_manually_edited
            if doc_number is not None:
                doc.doc_number = doc_number
            if doc_date is not None:
                doc.doc_date = doc_date
            if entity_name is not None:
                doc.entity_name = entity_name
            if total_amount is not None:
                doc.total_amount = total_amount
            if data_payload is not None:
                doc.data_payload = data_payload
            doc.updated_at = now_str
            return True
    except Exception as e:
        logger.error(f"Failed to approve document '{document_id}': {e}")
        return False


def update_document_to_rejected(document_id: str, reason: str, confirmed_by: str = SystemUserId.DEV_ADMIN) -> bool:
    """
    Marks a document as REJECTED and closes it using Atomic Guard (is_closed == 0).
    """
    try:
        with get_db_session() as session:
            doc = session.scalars(
                select(Document).where(Document.document_id == document_id, Document.is_closed == 0)
            ).first()
            if not doc:
                logger.warning(f"Cannot reject document '{document_id}': Document does not exist or is already closed.")
                return False
            now_str = datetime.now(timezone.utc).isoformat()
            doc.status_code = "REJECTED"
            doc.is_closed = 1
            doc.is_locked = 0
            doc.locked_by = None
            doc.locked_at = None
            doc.confirmed_by = confirmed_by
            doc.confirmed_at = now_str
            doc.error_reason = reason
            doc.updated_at = now_str
            return True
    except Exception as e:
        logger.error(f"Failed to reject document '{document_id}': {e}")
        return False


# =========================================================================
# Airline Ticket Hold Concurrency Lock Services (15-Min TTL & Auto-Release)
# =========================================================================

def acquire_document_lock(
    document_id: str,
    user_id: str,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS
) -> tuple[bool, str, dict | None]:
    """
    Acquires an exclusive 15-minute editing lock on a document (Airline Ticket Hold pattern).
    
    If the document is already locked by another user but the lock duration exceeds
    ttl_seconds, the stale lock is automatically released and granted to the new user.
    
    Returns:
        tuple[bool, str, dict | None]: (success, status_message, document_dict)
    """
    try:
        with get_db_session() as session:
            doc = session.scalars(select(Document).filter_by(document_id=document_id)).first()
            if not doc:
                return False, "DOCUMENT_NOT_FOUND", None
            if doc.is_closed == 1:
                return False, "DOCUMENT_ALREADY_CLOSED", doc.to_dict()

            now = datetime.now(timezone.utc)
            now_str = now.isoformat()

            # Check if existing lock is expired
            is_expired = False
            if doc.is_locked == 1 and doc.locked_at:
                try:
                    lock_time = datetime.fromisoformat(doc.locked_at)
                    if lock_time.tzinfo is None:
                        lock_time = lock_time.replace(tzinfo=timezone.utc)
                    elapsed = (now - lock_time).total_seconds()
                    if elapsed > ttl_seconds:
                        is_expired = True
                except Exception:
                    is_expired = True

            # Grant lock if: unlocked, owned by same user, or expired
            if doc.is_locked == 0 or doc.locked_by == user_id or is_expired:
                doc.is_locked = 1
                doc.locked_by = user_id
                doc.locked_at = now_str
                doc.updated_at = now_str
                return True, "LOCK_ACQUIRED", doc.to_dict()

            # Otherwise, locked by another active user
            return False, f"LOCKED_BY_{doc.locked_by}", doc.to_dict()
    except Exception as e:
        logger.error(f"Failed to acquire lock for document '{document_id}': {e}")
        return False, f"ERROR: {e}", None


def renew_document_lock(
    document_id: str,
    user_id: str,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS
) -> bool:
    """
    Renews/extends the 15-minute lock lease for the current holder (Heartbeat Ping / Extension Modal).
    """
    try:
        with get_db_session() as session:
            doc = session.scalars(select(Document).filter_by(document_id=document_id)).first()
            if not doc or doc.is_closed == 1 or doc.is_locked == 0:
                return False
            if doc.locked_by == user_id or user_id == SystemUserId.DEV_ADMIN:
                now_str = datetime.now(timezone.utc).isoformat()
                doc.locked_at = now_str
                doc.updated_at = now_str
                return True
            return False
    except Exception as e:
        logger.error(f"Failed to renew lock for document '{document_id}': {e}")
        return False


def release_document_lock(
    document_id: str,
    user_id: str,
    force: bool = False
) -> bool:
    """
    Releases an editing lock and returns the document back to the shared queue.
    """
    try:
        with get_db_session() as session:
            doc = session.scalars(select(Document).filter_by(document_id=document_id)).first()
            if not doc:
                return False
            if doc.is_locked == 0:
                return True
            if doc.locked_by == user_id or force or user_id == SystemUserId.DEV_ADMIN:
                doc.is_locked = 0
                doc.locked_by = None
                doc.locked_at = None
                doc.updated_at = datetime.now(timezone.utc).isoformat()
                return True
            return False
    except Exception as e:
        logger.error(f"Failed to release lock for document '{document_id}': {e}")
        return False


def get_document_lock_status(
    document_id: str,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS
) -> dict:
    """
    Retrieves real-time concurrency lock status and remaining lease duration in seconds.
    """
    try:
        with get_db_session() as session:
            doc = session.scalars(select(Document).filter_by(document_id=document_id)).first()
            if not doc:
                return {"is_locked": False, "locked_by": None, "locked_at": None, "remaining_seconds": 0.0, "is_expired": True}
            if doc.is_locked == 0 or not doc.locked_at:
                return {"is_locked": False, "locked_by": None, "locked_at": None, "remaining_seconds": 0.0, "is_expired": True}

            now = datetime.now(timezone.utc)
            try:
                lock_time = datetime.fromisoformat(doc.locked_at)
                if lock_time.tzinfo is None:
                    lock_time = lock_time.replace(tzinfo=timezone.utc)
                elapsed = (now - lock_time).total_seconds()
                remaining = max(0.0, float(ttl_seconds) - elapsed)
                is_expired = remaining <= 0.0
            except Exception:
                remaining = 0.0
                is_expired = True

            return {
                "is_locked": doc.is_locked == 1 and not is_expired,
                "locked_by": doc.locked_by,
                "locked_at": doc.locked_at,
                "remaining_seconds": round(remaining, 1),
                "is_expired": is_expired
            }
    except Exception as e:
        logger.error(f"Failed to get lock status for document '{document_id}': {e}")
        return {"is_locked": False, "locked_by": None, "locked_at": None, "remaining_seconds": 0.0, "is_expired": True}


def update_document_status(document_id: str, status_code: str, error_reason: str = None) -> bool:
    """
    Updates the status code and optional error reason of a document using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            doc = session.scalars(select(Document).filter_by(document_id=document_id)).first()
            if not doc:
                return False
            doc.status_code = status_code
            if error_reason is not None:
                doc.error_reason = error_reason
            doc.updated_at = datetime.now(timezone.utc).isoformat()
            return True
    except Exception as e:
        logger.error(f"Failed to update document status for '{document_id}': {e}")
        return False


def update_document_to_failed(document_id: str, error_reason: str) -> bool:
    """Marks a document as FAILED with error reason."""
    return update_document_status(document_id, status_code="FAILED", error_reason=error_reason)


def update_document_payload(
    document_id: str,
    data_payload: str = None,
    status_code: str = None,
    doc_number: str = None,
    doc_date: str = None,
    entity_name: str = None,
    total_amount: float = None,
    is_manually_edited: int = None
) -> bool:
    """
    Updates the JSON data payload for an open document using Atomic Guard (is_closed == 0).
    """
    try:
        with get_db_session() as session:
            doc = session.scalars(
                select(Document).where(Document.document_id == document_id, Document.is_closed == 0)
            ).first()
            if not doc:
                logger.warning(f"Cannot update payload for '{document_id}': Document does not exist or is closed.")
                return False
            now_str = datetime.now(timezone.utc).isoformat()
            if data_payload is not None:
                doc.data_payload = data_payload
            if status_code is not None:
                doc.status_code = status_code
            if doc_number is not None:
                doc.doc_number = doc_number
            if doc_date is not None:
                doc.doc_date = doc_date
            if entity_name is not None:
                doc.entity_name = entity_name
            if total_amount is not None:
                doc.total_amount = total_amount
            if is_manually_edited is not None:
                doc.is_manually_edited = is_manually_edited
            doc.updated_at = now_str
            return True
    except Exception as e:
        logger.error(f"Failed to update document payload for '{document_id}': {e}")
        return False


def update_document_metadata(
    document_id: str,
    overall_confidence: float = None,
    confidence_level: str = None,
    is_blurry: int = None,
    is_ambiguous: int = None,
    has_ambiguous_fields: int = None,
    confidence_notes: str = None,
    review_priority: str = None,
    is_auto_approved: int = None,
    auto_approved: int = None,
    cost_usd: float = None,
    cost_thb: float = None,
    is_free_tier: int = None
) -> bool:
    """
    Updates evaluation metadata and cost columns for a document using Pure SQLAlchemy 2.0 ORM.
    """
    final_auto_approved = is_auto_approved if is_auto_approved is not None else (auto_approved if auto_approved is not None else None)
    final_ambiguous = is_ambiguous if is_ambiguous is not None else (has_ambiguous_fields if has_ambiguous_fields is not None else None)

    try:
        with get_db_session() as session:
            doc = session.scalars(select(Document).filter_by(document_id=document_id)).first()
            if not doc:
                return False
            now_str = datetime.now(timezone.utc).isoformat()
            if overall_confidence is not None:
                doc.overall_confidence = overall_confidence
            if confidence_level is not None:
                doc.confidence_level = confidence_level
            if is_blurry is not None:
                doc.is_blurry = is_blurry
            if final_ambiguous is not None:
                doc.is_ambiguous = final_ambiguous
            if confidence_notes is not None:
                doc.confidence_notes = confidence_notes
            if review_priority is not None:
                doc.review_priority = review_priority
            if final_auto_approved is not None:
                doc.is_auto_approved = final_auto_approved
            if cost_usd is not None:
                doc.cost_usd = cost_usd
            if cost_thb is not None:
                doc.cost_thb = cost_thb
            if is_free_tier is not None:
                doc.is_free_tier = is_free_tier
            doc.updated_at = now_str
            return True
    except Exception as e:
        logger.error(f"Failed to update document metadata for '{document_id}': {e}")
        return False


def search_documents(
    domain_id: str,
    source_id: str = None,
    start_date: str = None,
    end_date: str = None,
    keyword: str = None,
    company_id: str = None
) -> list[dict]:
    """
    Performs dynamic lookup of documents using Pure SQLAlchemy 2.0 ORM.
    Optionally filters by company_id.
    """
    try:
        with get_db_session() as session:
            stmt = select(Document, ProcessedBatch).join(
                ProcessedBatch, Document.batch_id == ProcessedBatch.batch_id
            ).where(Document.domain_id == domain_id)

            if company_id:
                stmt = stmt.where(Document.company_id == company_id)

            if source_id and source_id != "All":
                stmt = stmt.where(Document.source_id == source_id)

            if start_date:
                stmt = stmt.where(Document.doc_date >= start_date)

            if end_date:
                stmt = stmt.where(Document.doc_date <= end_date)

            if keyword:
                like_kw = f"%{keyword}%"
                stmt = stmt.where(
                    or_(
                        Document.doc_number.ilike(like_kw),
                        Document.entity_name.ilike(like_kw),
                        Document.search_text.ilike(like_kw)
                    )
                )

            stmt = stmt.order_by(Document.created_at.desc())
            results = session.execute(stmt).all()
            docs = []
            for doc, batch in results:
                d = doc.to_dict()
                d["original_filename"] = batch.original_filename
                d["original_pdf_name"] = batch.original_filename
                d["storage_path"] = batch.storage_path
                docs.append(d)
            return docs
    except Exception as e:
        logger.error(f"Failed to search documents: {e}")
        return []


def get_unextracted_batches(status_codes: list[str] = None, company_id: str = None) -> list[dict]:
    """
    Fetches batches that contain pages matching specified status codes using Pure SQLAlchemy 2.0 ORM.
    Optionally filters by company_id.
    """
    if status_codes is None:
        status_codes = [DocumentStatusCode.PREPROCESSED, DocumentStatusCode.PENDING]

    try:
        with get_db_session() as session:
            stmt = select(
                ProcessedBatch.batch_id,
                ProcessedBatch.company_id,
                ProcessedBatch.original_filename,
                ProcessedBatch.storage_path,
                ProcessedBatch.total_pages
            ).join(
                DocumentPage, ProcessedBatch.batch_id == DocumentPage.batch_id
            ).where(
                DocumentPage.status_code.in_(status_codes)
            ).distinct()

            if company_id:
                stmt = stmt.where(ProcessedBatch.company_id == company_id)

            batches = session.execute(stmt).all()

            return [
                {
                    "batch_id": b.batch_id,
                    "company_id": b.company_id,
                    "original_filename": b.original_filename,
                    "original_pdf_name": b.original_filename,
                    "storage_path": b.storage_path,
                    "total_pages": b.total_pages
                }
                for b in batches
            ]
    except Exception as e:
        logger.error(f"Failed to fetch unextracted batches: {e}")
        return []


def get_pages_by_status(status_codes: list[str] = None, company_id: str = None) -> list[dict]:
    """
    Fetches document page records joined with batch info matching given status codes using Pure SQLAlchemy 2.0 ORM.
    Optionally filters by company_id.
    """
    if status_codes is None:
        status_codes = [DocumentStatusCode.EXTRACTED]

    try:
        with get_db_session() as session:
            stmt = select(
                DocumentPage,
                ProcessedBatch.original_filename,
                ProcessedBatch.storage_path
            ).join(
                ProcessedBatch, DocumentPage.batch_id == ProcessedBatch.batch_id
            ).where(
                DocumentPage.status_code.in_(status_codes)
            )

            if company_id:
                stmt = stmt.where(ProcessedBatch.company_id == company_id)

            stmt = stmt.order_by(
                DocumentPage.batch_id.asc(),
                DocumentPage.page_number.asc()
            )

            results = session.execute(stmt).all()

            pages = []
            for dp, orig_name, storage_path in results:
                d = dp.to_dict()
                d["original_filename"] = orig_name
                d["original_pdf_name"] = orig_name
                d["storage_path"] = storage_path
                pages.append(d)
            return pages
    except Exception as e:
        logger.error(f"Failed to fetch pages by status: {e}")
        return []


def get_documents_for_export(domain_id: str, status_codes: list[str] = None, company_id: str = None) -> list[dict]:
    """
    Fetches approved/processed document records joined with batch info for report exporters using Pure SQLAlchemy 2.0 ORM.
    Optionally filters by company_id.
    """
    if status_codes is None:
        status_codes = [DocumentStatusCode.APPROVED, DocumentStatusCode.PROCESSED]

    try:
        with get_db_session() as session:
            stmt = select(
                Document,
                ProcessedBatch.original_filename
            ).join(
                ProcessedBatch, Document.batch_id == ProcessedBatch.batch_id
            ).where(
                Document.domain_id == domain_id,
                Document.status_code.in_(status_codes)
            )

            if company_id:
                stmt = stmt.where(Document.company_id == company_id)

            stmt = stmt.order_by(Document.created_at.asc())
            results = session.execute(stmt).all()

            docs = []
            for doc, orig_name in results:
                d = doc.to_dict()
                d["original_filename"] = orig_name
                d["original_pdf_name"] = orig_name
                docs.append(d)
            return docs
    except Exception as e:
        logger.error(f"Failed to fetch documents for export: {e}")
        return []
