"""Ingestion Batch and Physical BatchPage repository using Pure SQLAlchemy 2.0 ORM."""

import hashlib
from datetime import datetime, timezone
from typing import List, Tuple
from sqlalchemy import select, update, or_

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import DefaultIdentifier, DocumentStatusCode
from ..engine import get_db_session
from ..models import Company, Batch, BatchPage, DocumentControl


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
            stmt = select(Batch).filter_by(file_hash=file_hash)
            if company_id:
                stmt = stmt.where(Batch.company_id == company_id)
            batch = session.scalars(stmt).first()
            if batch:
                first_doc = session.scalars(select(DocumentControl).filter_by(batch_id=batch.batch_id)).first()
                metadata = {
                    "batch_id": batch.batch_id,
                    "company_id": batch.company_id,
                    "original_filename": batch.original_filename,
                    "original_pdf_name": batch.original_filename,
                    "created_at": batch.created_at,
                    "status": first_doc.status_code if first_doc else DocumentStatusCode.PENDING,
                    "doc_type_id": first_doc.doc_type_id if first_doc else DefaultIdentifier.DOC_TYPE,
                    "merchant_id": DefaultIdentifier.NO_TAX_LABEL,
                    "source": DefaultIdentifier.NO_TAX_LABEL
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
            batch = session.scalars(select(Batch).filter_by(batch_id=batch_id)).first()
            if batch:
                if target_cid:
                    batch.company_id = target_cid
                batch.original_filename = filename
                batch.total_pages = total_pages
                batch.storage_path = storage_path
                batch.file_hash = file_hash
            else:
                batch = Batch(
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


def create_page(
    page_id: str,
    batch_id: str,
    page_number: int,
    image_path: str,
    status_code: str,
    chunk_index: int = 1,
    error_reason: str = None
) -> bool:
    """Inserts or updates a physical batch page record."""
    try:
        with get_db_session() as session:
            created_at = datetime.now(timezone.utc).isoformat()
            page = session.scalars(select(BatchPage).filter_by(page_id=page_id)).first()
            if page:
                page.batch_id = batch_id
                page.page_number = page_number
                page.chunk_index = chunk_index
                page.image_path = image_path
                page.status_code = status_code
                page.error_reason = error_reason
            else:
                page = BatchPage(
                    page_id=page_id,
                    batch_id=batch_id,
                    page_number=page_number,
                    chunk_index=chunk_index,
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
    """Updates an existing batch page record."""
    try:
        with get_db_session() as session:
            page = session.scalars(select(BatchPage).filter_by(page_id=page_id)).first()
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
    """Convenience helper to update status and error reason of a page."""
    return update_page(page_id, status_code=status_code, error_reason=error_reason)


def update_pages_status_batch(updates: List[Tuple[str, str | None, str, int]]) -> bool:
    """Batch update page statuses using Pure SQLAlchemy 2.0 ORM."""
    try:
        with get_db_session() as session:
            for status_code, error_reason, batch_id, page_number in updates:
                stmt = select(BatchPage).filter_by(batch_id=batch_id, page_number=page_number)
                page = session.scalars(stmt).first()
                if page:
                    page.status_code = status_code
                    page.error_reason = error_reason
            return True
    except Exception as e:
        logger.error(f"Failed to batch update page statuses: {e}")
        return False


def get_batch_pages(batch_id: str) -> list[dict]:
    """Retrieves all pages belonging to a batch."""
    try:
        with get_db_session() as session:
            stmt = select(BatchPage).filter_by(batch_id=batch_id).order_by(BatchPage.page_number.asc())
            pages = session.scalars(stmt).all()
            return [p.to_dict() for p in pages]
    except Exception as e:
        logger.error(f"Failed to get pages for batch '{batch_id}': {e}")
        return []


def get_unextracted_batches(status_codes: list[str] = None, company_id: str = None, batch_id: str = None) -> list[dict]:
    """Fetches batches that contain pages matching specified status codes."""
    if status_codes is None:
        status_codes = [DocumentStatusCode.PREPROCESSED, DocumentStatusCode.PENDING]

    try:
        with get_db_session() as session:
            stmt = select(
                Batch.batch_id,
                Batch.company_id,
                Batch.original_filename,
                Batch.storage_path,
                Batch.total_pages
            ).join(
                BatchPage, Batch.batch_id == BatchPage.batch_id
            ).where(
                BatchPage.status_code.in_(status_codes)
            ).distinct()

            if company_id:
                stmt = stmt.where(Batch.company_id == company_id)
            if batch_id:
                stmt = stmt.where(Batch.batch_id == batch_id)

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
        logger.error(f"Failed to get unextracted batches: {e}")
        return []


def get_unextracted_batch_pages(status_codes: list[str] = None, company_id: str = None, batch_id: str = None) -> list[dict]:
    """Retrieves individual unextracted pages joined with batch metadata."""
    if status_codes is None:
        status_codes = [DocumentStatusCode.PREPROCESSED, DocumentStatusCode.PENDING]

    try:
        with get_db_session() as session:
            stmt = select(
                BatchPage,
                Batch.original_filename,
                Batch.storage_path
            ).join(
                Batch, BatchPage.batch_id == Batch.batch_id
            ).where(
                BatchPage.status_code.in_(status_codes)
            )

            if company_id:
                stmt = stmt.where(Batch.company_id == company_id)
            if batch_id:
                stmt = stmt.where(BatchPage.batch_id == batch_id)

            stmt = stmt.order_by(
                BatchPage.batch_id.asc(),
                BatchPage.page_number.asc()
            )

            results = session.execute(stmt).all()
            pages = []
            for p, original_filename, storage_path in results:
                d = p.to_dict()
                d["original_filename"] = original_filename
                d["original_pdf_name"] = original_filename
                d["storage_path"] = storage_path
                pages.append(d)
            return pages
    except Exception as e:
        logger.error(f"Failed to get unextracted batch pages: {e}")
        return []


def get_unextracted_chunk_indices(batch_id: str) -> list[int]:
    """Retrieves unique chunk indices in a batch where not all pages are EXTRACTED."""
    try:
        with get_db_session() as session:
            stmt = select(BatchPage.chunk_index).where(
                BatchPage.batch_id == batch_id,
                BatchPage.status_code != DocumentStatusCode.EXTRACTED
            ).distinct().order_by(BatchPage.chunk_index.asc())
            return list(session.scalars(stmt).all())
    except Exception as e:
        logger.error(f"Failed to get unextracted chunks for batch '{batch_id}': {e}")
        return []


def get_pages_for_chunk(batch_id: str, chunk_index: int) -> list[dict]:
    """Retrieves all pages assigned to a specific chunk sequence."""
    try:
        with get_db_session() as session:
            stmt = select(BatchPage).where(
                BatchPage.batch_id == batch_id,
                BatchPage.chunk_index == chunk_index
            ).order_by(BatchPage.page_number.asc())
            pages = session.scalars(stmt).all()
            return [p.to_dict() for p in pages]
    except Exception as e:
        logger.error(f"Failed to get pages for batch '{batch_id}' chunk '{chunk_index}': {e}")
        return []


def update_chunk_status(batch_id: str, chunk_index: int, status_code: str, error_reason: str = None) -> bool:
    """Batch updates all pages within a specific chunk index."""
    try:
        with get_db_session() as session:
            stmt = update(BatchPage).where(
                BatchPage.batch_id == batch_id,
                BatchPage.chunk_index == chunk_index
            ).values(
                status_code=status_code,
                error_reason=error_reason
            )
            session.execute(stmt)
            return True
    except Exception as e:
        logger.error(f"Failed to update chunk status for batch '{batch_id}' chunk '{chunk_index}': {e}")
        return False


get_unextracted_chunks_for_batch = get_unextracted_chunk_indices
get_pages_by_chunk = get_pages_for_chunk
update_chunk_pages_status = update_chunk_status


def get_page_by_id(page_id: str) -> dict | None:
    """Retrieves a single page record by page_id."""
    try:
        with get_db_session() as session:
            page = session.scalars(select(BatchPage).filter_by(page_id=page_id)).first()
            return page.to_dict() if page else None
    except Exception as e:
        logger.error(f"Failed to get page '{page_id}': {e}")
        return None


def get_pages_by_status(status_codes: list[str], company_id: str = None, batch_id: str = None) -> list[dict]:
    """Fetches pages matching specified status codes joined with batch metadata."""
    try:
        with get_db_session() as session:
            stmt = select(
                BatchPage,
                Batch.original_filename,
                Batch.storage_path
            ).join(
                Batch, BatchPage.batch_id == Batch.batch_id
            ).where(
                BatchPage.status_code.in_(status_codes)
            )

            if company_id:
                stmt = stmt.where(Batch.company_id == company_id)
            if batch_id:
                stmt = stmt.where(BatchPage.batch_id == batch_id)

            stmt = stmt.order_by(
                BatchPage.batch_id.asc(),
                BatchPage.page_number.asc()
            )

            results = session.execute(stmt).all()
            pages = []
            for p, original_filename, storage_path in results:
                d = p.to_dict()
                d["original_filename"] = original_filename
                d["original_pdf_name"] = original_filename
                d["storage_path"] = storage_path
                pages.append(d)
            return pages
    except Exception as e:
        logger.error(f"Failed to get pages by status: {e}")
        return []


def get_all_pages(batch_id: str = None, company_id: str = None) -> list[dict]:
    """Retrieves all pages joined with batch metadata."""
    try:
        with get_db_session() as session:
            stmt = select(
                BatchPage,
                Batch.original_filename
            ).join(
                Batch, BatchPage.batch_id == Batch.batch_id
            )

            if company_id:
                stmt = stmt.where(Batch.company_id == company_id)
            if batch_id:
                stmt = stmt.where(BatchPage.batch_id == batch_id)

            stmt = stmt.order_by(
                BatchPage.batch_id.asc(),
                BatchPage.page_number.asc()
            )

            results = session.execute(stmt).all()
            pages = []
            for p, original_filename in results:
                d = p.to_dict()
                d["original_filename"] = original_filename
                d["original_pdf_name"] = original_filename
                pages.append(d)
            return pages
    except Exception as e:
        logger.error(f"Failed to get all pages: {e}")
        return []
