"""DocumentControl universal supertype repository using Pure SQLAlchemy 2.0 ORM."""

from datetime import datetime, timezone
from sqlalchemy import select, or_, and_, desc

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import DefaultIdentifier, DocumentStatusCode, SystemUserId
from ..engine import get_db_session
from ..models import Company, Batch, BatchPage, DocumentControl, Merchant, ExpenseReceipt

DEFAULT_LOCK_TTL_SECONDS = 900  # 15 minutes Airline Ticket Hold duration


def create_document(
    document_id: str,
    batch_id: str,
    doc_type_id: str = None,
    merchant_id: str = None,
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
    """Inserts or updates a DocumentControl record and associated ExpenseReceipt if applicable."""
    final_dt = doc_type_id or DefaultIdentifier.DOC_TYPE
    final_auto_approved = is_auto_approved if is_auto_approved is not None else (auto_approved or 0)
    final_ambiguous = is_ambiguous if is_ambiguous is not None else (has_ambiguous_fields or 0)

    try:
        with get_db_session() as session:
            target_cid = company_id
            if not target_cid:
                batch_obj = session.scalars(select(Batch).filter_by(batch_id=batch_id)).first()
                if batch_obj and batch_obj.company_id:
                    target_cid = batch_obj.company_id
                else:
                    def_comp = session.scalars(select(Company).filter_by(company_code=DefaultIdentifier.COMPANY_CODE)).first()
                    if def_comp:
                        target_cid = def_comp.company_id

            raw_merchant_key = merchant_id
            final_merchant_id = None
            if raw_merchant_key:
                merch_exists = session.scalars(
                    select(Merchant.merchant_id).where(
                        or_(
                            Merchant.merchant_id == raw_merchant_key,
                            Merchant.short_name == raw_merchant_key,
                            Merchant.file_prefix == raw_merchant_key
                        )
                    )
                ).first()
                final_merchant_id = merch_exists

            if not final_merchant_id:
                fallback_merch = session.scalars(
                    select(Merchant.merchant_id).where(
                        or_(
                            Merchant.merchant_id == DefaultIdentifier.NO_TAX_ID,
                            Merchant.short_name == DefaultIdentifier.NO_TAX_ID,
                            Merchant.file_prefix == DefaultIdentifier.NO_TAX_ID
                        )
                    )
                ).first()
                if not fallback_merch:
                    fallback_merch = session.scalars(select(Merchant.merchant_id)).first()
                final_merchant_id = fallback_merch

            created_at = datetime.now(timezone.utc).isoformat()
            doc = session.scalars(select(DocumentControl).filter_by(document_id=document_id)).first()
            if doc:
                if target_cid:
                    doc.company_id = target_cid
                doc.batch_id = batch_id
                doc.doc_type_id = final_dt
                doc.status_code = status_code
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
                doc = DocumentControl(
                    document_id=document_id,
                    company_id=target_cid,
                    batch_id=batch_id,
                    doc_type_id=final_dt,
                    status_code=status_code,
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

            if final_merchant_id and (doc_number or doc_date or entity_name or total_amount is not None or final_merchant_id):
                receipt = session.scalars(select(ExpenseReceipt).filter_by(document_id=document_id)).first()
                if not receipt:
                    receipt = ExpenseReceipt(
                        receipt_id=document_id,
                        company_id=target_cid,
                        document_id=document_id,
                        merchant_id=final_merchant_id,
                        doc_number=doc_number,
                        transaction_date=doc_date,
                        merchant_name=entity_name,
                        expense_category=None,
                        subtotal=total_amount or 0.0,
                        vat_amount=0.0,
                        net_amount=total_amount or 0.0,
                        created_at=created_at
                    )
                    session.add(receipt)
                else:
                    if doc_number is not None:
                        receipt.doc_number = doc_number
                    if doc_date is not None:
                        receipt.transaction_date = doc_date
                    if entity_name is not None:
                        receipt.merchant_name = entity_name
                    if final_merchant_id is not None:
                        receipt.merchant_id = final_merchant_id
                    if total_amount is not None:
                        receipt.net_amount = total_amount

            return True
    except Exception as e:
        logger.error(f"Failed to create document '{document_id}': {e}")
        return False


def link_pages_to_document(document_id: str, page_ids: list[str]) -> bool:
    """Associates physical pages to a document record."""
    try:
        with get_db_session() as session:
            for pid in page_ids:
                page = session.scalars(select(BatchPage).filter_by(page_id=pid)).first()
                if page:
                    page.document_id = document_id
            return True
    except Exception as e:
        logger.error(f"Failed to link pages to document '{document_id}': {e}")
        return False


def get_document_by_id(document_id: str) -> dict | None:
    """Retrieves full details of a specific document joined with batch and receipt subtype."""
    try:
        with get_db_session() as session:
            doc = session.scalars(select(DocumentControl).filter_by(document_id=document_id)).first()
            if not doc:
                return None
            doc_dict = doc.to_dict()
            batch = session.scalars(select(Batch).filter_by(batch_id=doc.batch_id)).first()
            if batch:
                doc_dict["original_filename"] = batch.original_filename
                doc_dict["original_pdf_name"] = batch.original_filename
                doc_dict["storage_path"] = batch.storage_path

            receipt = session.scalars(select(ExpenseReceipt).filter_by(document_id=document_id)).first()
            if receipt:
                doc_dict["doc_number"] = receipt.doc_number if hasattr(receipt, "doc_number") else ""
                doc_dict["doc_date"] = receipt.transaction_date or ""
                doc_dict["merchant_id"] = receipt.merchant_id or ""
                doc_dict["merchant_name"] = receipt.merchant_name or ""
                doc_dict["entity_name"] = receipt.merchant_name or ""
                doc_dict["total_amount"] = receipt.net_amount or 0.0
                doc_dict["subtotal"] = receipt.subtotal or 0.0
                doc_dict["vat_amount"] = receipt.vat_amount or 0.0
                doc_dict["net_amount"] = receipt.net_amount or 0.0
                doc_dict["expense_category"] = receipt.expense_category or ""
                doc_dict["payment_method"] = receipt.payment_method or ""
            else:
                doc_dict["doc_number"] = ""
                doc_dict["doc_date"] = ""
                doc_dict["merchant_id"] = ""
                doc_dict["merchant_name"] = ""
                doc_dict["entity_name"] = ""
                doc_dict["total_amount"] = 0.0
            return doc_dict
    except Exception as e:
        logger.error(f"Failed to get document '{document_id}': {e}")
        return None


def get_document_pages(document_id: str) -> list[dict]:
    """Retrieves all pages associated with a specific document."""
    try:
        with get_db_session() as session:
            stmt = select(BatchPage).filter_by(document_id=document_id).order_by(BatchPage.page_number.asc())
            pages = session.scalars(stmt).all()
            return [p.to_dict() for p in pages]
    except Exception as e:
        logger.error(f"Failed to get pages for document '{document_id}': {e}")
        return []


def get_pending_documents(
    doc_type_id: str = None,
    merchant_id: str = None,
    company_id: str = None,
) -> list[dict]:
    """Retrieves documents waiting for review."""
    target_dt = doc_type_id
    target_merchant = merchant_id
    try:
        with get_db_session() as session:
            stmt = select(DocumentControl, Batch).join(
                Batch, DocumentControl.batch_id == Batch.batch_id
            ).where(
                DocumentControl.status_code.in_([
                    DocumentStatusCode.PENDING,
                    DocumentStatusCode.NEEDS_REVIEW,
                    DocumentStatusCode.PROCESSED,
                ])
            )

            if company_id:
                stmt = stmt.where(DocumentControl.company_id == company_id)
            if target_dt:
                stmt = stmt.where(DocumentControl.doc_type_id == target_dt)

            stmt = stmt.order_by(
                DocumentControl.review_priority.desc(),
                DocumentControl.created_at.desc()
            )

            results = session.execute(stmt).all()
            docs = []
            for doc, batch in results:
                d = doc.to_dict()
                d["original_filename"] = batch.original_filename
                d["original_pdf_name"] = batch.original_filename
                d["storage_path"] = batch.storage_path
                receipt = session.scalars(select(ExpenseReceipt).filter_by(document_id=doc.document_id)).first()
                if receipt:
                    d["doc_number"] = receipt.doc_number if hasattr(receipt, "doc_number") else ""
                    d["doc_date"] = receipt.transaction_date or ""
                    d["merchant_id"] = receipt.merchant_id or ""
                    d["merchant_name"] = receipt.merchant_name or ""
                    d["entity_name"] = receipt.merchant_name or ""
                    d["total_amount"] = receipt.net_amount or 0.0
                    d["subtotal"] = receipt.subtotal or 0.0
                    d["vat_amount"] = receipt.vat_amount or 0.0
                    d["net_amount"] = receipt.net_amount or 0.0
                    d["expense_category"] = receipt.expense_category or ""
                    d["payment_method"] = receipt.payment_method or ""
                else:
                    d["doc_number"] = ""
                    d["doc_date"] = ""
                    d["merchant_id"] = ""
                    d["merchant_name"] = ""
                    d["entity_name"] = ""
                    d["total_amount"] = 0.0
                if target_merchant and d["merchant_id"] != target_merchant:
                    continue
                docs.append(d)
            return docs
    except Exception as e:
        logger.error(f"Failed to get pending documents: {e}")
        return []


def get_all_documents(
    doc_type_id: str = None,
    merchant_id: str = None,
    status_code: str = None,
    company_id: str = None,
) -> list[dict]:
    """Retrieves all documents matching criteria."""
    target_dt = doc_type_id
    target_merchant = merchant_id
    try:
        with get_db_session() as session:
            stmt = select(DocumentControl, Batch).join(
                Batch, DocumentControl.batch_id == Batch.batch_id
            )

            if company_id:
                stmt = stmt.where(DocumentControl.company_id == company_id)
            if target_dt:
                stmt = stmt.where(DocumentControl.doc_type_id == target_dt)
            if status_code:
                stmt = stmt.where(DocumentControl.status_code == status_code)

            stmt = stmt.order_by(DocumentControl.created_at.desc())
            results = session.execute(stmt).all()
            docs = []
            for doc, batch in results:
                d = doc.to_dict()
                d["original_filename"] = batch.original_filename
                d["original_pdf_name"] = batch.original_filename
                d["storage_path"] = batch.storage_path
                receipt = session.scalars(select(ExpenseReceipt).filter_by(document_id=doc.document_id)).first()
                if receipt:
                    d["doc_number"] = receipt.doc_number if hasattr(receipt, "doc_number") else ""
                    d["doc_date"] = receipt.transaction_date or ""
                    d["merchant_id"] = receipt.merchant_id or ""
                    d["merchant_name"] = receipt.merchant_name or ""
                    d["entity_name"] = receipt.merchant_name or ""
                    d["total_amount"] = receipt.net_amount or 0.0
                    d["subtotal"] = receipt.subtotal or 0.0
                    d["vat_amount"] = receipt.vat_amount or 0.0
                    d["net_amount"] = receipt.net_amount or 0.0
                    d["expense_category"] = receipt.expense_category or ""
                    d["payment_method"] = receipt.payment_method or ""
                else:
                    d["doc_number"] = ""
                    d["doc_date"] = ""
                    d["merchant_id"] = ""
                    d["merchant_name"] = ""
                    d["entity_name"] = ""
                    d["total_amount"] = 0.0
                if target_merchant and d["merchant_id"] != target_merchant:
                    continue
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
    """Marks a document as APPROVED and closes it using Atomic Guard (is_closed == 0)."""
    try:
        with get_db_session() as session:
            doc = session.scalars(
                select(DocumentControl).where(DocumentControl.document_id == document_id, DocumentControl.is_closed == 0)
            ).first()
            if not doc:
                logger.warning(f"Cannot approve document '{document_id}': DocumentControl does not exist or is already closed.")
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
            if data_payload is not None:
                doc.data_payload = data_payload
            doc.updated_at = now_str

            receipt = session.scalars(select(ExpenseReceipt).filter_by(document_id=document_id)).first()
            if receipt:
                if doc_number is not None:
                    receipt.doc_number = doc_number
                if doc_date is not None:
                    receipt.transaction_date = doc_date
                if entity_name is not None:
                    receipt.merchant_name = entity_name
                if total_amount is not None:
                    receipt.net_amount = total_amount
            return True
    except Exception as e:
        logger.error(f"Failed to approve document '{document_id}': {e}")
        return False


def update_document_to_rejected(document_id: str, reason: str, confirmed_by: str = SystemUserId.DEV_ADMIN) -> bool:
    """Marks a document as REJECTED and closes it using Atomic Guard (is_closed == 0)."""
    try:
        with get_db_session() as session:
            doc = session.scalars(
                select(DocumentControl).where(DocumentControl.document_id == document_id, DocumentControl.is_closed == 0)
            ).first()
            if not doc:
                logger.warning(f"Cannot reject document '{document_id}': DocumentControl does not exist or is already closed.")
                return False
            now_str = datetime.now(timezone.utc).isoformat()
            doc.status_code = DocumentStatusCode.REJECTED
            doc.error_reason = reason
            doc.is_closed = 1
            doc.is_locked = 0
            doc.locked_by = None
            doc.locked_at = None
            doc.confirmed_by = confirmed_by
            doc.confirmed_at = now_str
            doc.updated_at = now_str
            return True
    except Exception as e:
        logger.error(f"Failed to reject document '{document_id}': {e}")
        return False


def acquire_document_lock(
    document_id: str,
    user_id: str,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS
) -> tuple[bool, str, dict | None]:
    """Acquires an exclusive 15-minute editing lock on a document (Airline Ticket Hold pattern)."""
    try:
        with get_db_session() as session:
            doc = session.scalars(select(DocumentControl).filter_by(document_id=document_id)).first()
            if not doc:
                return False, "DOCUMENT_NOT_FOUND", None
            if doc.is_closed == 1:
                return False, "DOCUMENT_ALREADY_CLOSED", doc.to_dict()

            now = datetime.now(timezone.utc)
            now_str = now.isoformat()

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

            if doc.is_locked == 0 or doc.locked_by == user_id or is_expired:
                doc.is_locked = 1
                doc.locked_by = user_id
                doc.locked_at = now_str
                doc.updated_at = now_str
                return True, "LOCK_ACQUIRED", doc.to_dict()

            return False, f"LOCKED_BY_{doc.locked_by}", doc.to_dict()
    except Exception as e:
        logger.error(f"Failed to acquire lock for document '{document_id}': {e}")
        return False, f"ERROR: {e}", None


def renew_document_lock(
    document_id: str,
    user_id: str,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS
) -> bool:
    """Renews/extends the 15-minute lock lease for the current holder."""
    try:
        with get_db_session() as session:
            doc = session.scalars(select(DocumentControl).filter_by(document_id=document_id)).first()
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
    """Releases an editing lock and returns the document back to the shared queue."""
    try:
        with get_db_session() as session:
            doc = session.scalars(select(DocumentControl).filter_by(document_id=document_id)).first()
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
    """Retrieves real-time concurrency lock status and remaining lease duration in seconds."""
    try:
        with get_db_session() as session:
            doc = session.scalars(select(DocumentControl).filter_by(document_id=document_id)).first()
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
    """Updates the status code and optional error reason of a document."""
    try:
        with get_db_session() as session:
            doc = session.scalars(select(DocumentControl).filter_by(document_id=document_id)).first()
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
    """Updates the JSON data payload for an open document using Atomic Guard (is_closed == 0)."""
    try:
        with get_db_session() as session:
            doc = session.scalars(
                select(DocumentControl).where(DocumentControl.document_id == document_id, DocumentControl.is_closed == 0)
            ).first()
            if not doc:
                logger.warning(f"Cannot update payload for '{document_id}': DocumentControl does not exist or is closed.")
                return False
            now_str = datetime.now(timezone.utc).isoformat()
            if data_payload is not None:
                doc.data_payload = data_payload
            if status_code is not None:
                doc.status_code = status_code
            if is_manually_edited is not None:
                doc.is_manually_edited = is_manually_edited
            doc.updated_at = now_str

            receipt = session.scalars(select(ExpenseReceipt).filter_by(document_id=document_id)).first()
            if receipt:
                if doc_number is not None:
                    receipt.doc_number = doc_number
                if doc_date is not None:
                    receipt.transaction_date = doc_date
                if entity_name is not None:
                    receipt.merchant_name = entity_name
                if total_amount is not None:
                    receipt.net_amount = total_amount
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
    """Updates evaluation metadata and cost columns for a document."""
    final_auto_approved = is_auto_approved if is_auto_approved is not None else (auto_approved if auto_approved is not None else None)
    final_ambiguous = is_ambiguous if is_ambiguous is not None else (has_ambiguous_fields if has_ambiguous_fields is not None else None)

    try:
        with get_db_session() as session:
            doc = session.scalars(select(DocumentControl).filter_by(document_id=document_id)).first()
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
    doc_type_id: str = None,
    merchant_id: str = None,
    start_date: str = None,
    end_date: str = None,
    keyword: str = None,
    company_id: str = None,
) -> list[dict]:
    """Performs dynamic lookup of documents."""
    target_dt = doc_type_id or DefaultIdentifier.DOC_TYPE
    target_merchant = merchant_id
    try:
        with get_db_session() as session:
            stmt = select(DocumentControl, Batch).join(
                Batch, DocumentControl.batch_id == Batch.batch_id
            ).where(DocumentControl.doc_type_id == target_dt)

            if company_id:
                stmt = stmt.where(DocumentControl.company_id == company_id)

            if keyword and keyword.strip():
                kw = f"%{keyword.strip()}%"
                stmt = stmt.where(
                    or_(
                        DocumentControl.search_text.ilike(kw),
                        Batch.original_filename.ilike(kw)
                    )
                )

            stmt = stmt.order_by(DocumentControl.created_at.desc())
            results = session.execute(stmt).all()
            docs = []
            for doc, batch in results:
                d = doc.to_dict()
                d["original_filename"] = batch.original_filename
                d["original_pdf_name"] = batch.original_filename
                d["storage_path"] = batch.storage_path
                receipt = session.scalars(select(ExpenseReceipt).filter_by(document_id=doc.document_id)).first()
                if receipt:
                    d["doc_number"] = receipt.doc_number if hasattr(receipt, "doc_number") else ""
                    d["doc_date"] = receipt.transaction_date or ""
                    d["merchant_id"] = receipt.merchant_id or ""
                    d["merchant_name"] = receipt.merchant_name or ""
                    d["entity_name"] = receipt.merchant_name or ""
                    d["total_amount"] = receipt.net_amount or 0.0
                    d["subtotal"] = receipt.subtotal or 0.0
                    d["vat_amount"] = receipt.vat_amount or 0.0
                    d["net_amount"] = receipt.net_amount or 0.0
                    d["expense_category"] = receipt.expense_category or ""
                    d["payment_method"] = receipt.payment_method or ""
                else:
                    d["doc_number"] = ""
                    d["doc_date"] = ""
                    d["merchant_id"] = ""
                    d["merchant_name"] = ""
                    d["entity_name"] = ""
                    d["total_amount"] = 0.0

                if target_merchant and d["merchant_id"] != target_merchant:
                    continue
                if start_date and d["doc_date"] and d["doc_date"] < start_date:
                    continue
                if end_date and d["doc_date"] and d["doc_date"] > end_date:
                    continue

                docs.append(d)
            return docs
    except Exception as e:
        logger.error(f"Failed to search documents: {e}")
        return []
