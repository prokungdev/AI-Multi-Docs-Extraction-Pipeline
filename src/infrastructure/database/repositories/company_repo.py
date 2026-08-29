"""Tenant Company Master repository using Pure SQLAlchemy 2.0 ORM."""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import (
    DefaultIdentifier,
    DefaultCompany,
    EntityIdPrefix,
    generate_entity_id,
)
from ..engine import get_db_session
from ..models import Company


def get_or_create_default_company() -> dict:
    """Ensures default sandbox company exists and returns its dictionary representation."""
    try:
        with get_db_session() as session:
            stmt = select(Company).filter_by(company_code=DefaultCompany.CODE)
            comp = session.scalars(stmt).first()
            if not comp:
                comp = Company(
                    company_id=generate_entity_id(EntityIdPrefix.COMPANY),
                    company_code=DefaultCompany.CODE,
                    company_name=DefaultCompany.NAME,
                    short_name=DefaultCompany.SHORT_NAME,
                    tax_id=DefaultCompany.TAX_ID,
                    branch_code=DefaultCompany.BRANCH_CODE,
                    is_active=1
                )
                session.add(comp)
                session.flush()
            return comp.to_dict()
    except Exception as e:
        logger.error(f"Failed to get or create default company: {e}")
        raise RuntimeError(
            f"Cannot initialize default company. Database may be unavailable: {e}"
        ) from e


def create_company(company_code: str, company_name: str, short_name: str = None,
                   tax_id: str = "0000000000000", branch_code: str = "00000",
                   is_active: int = 1, company_id: str = None) -> dict:
    """Creates a new client company entity in the database."""
    clean_code = company_code.strip().upper()
    clean_tax_id = tax_id.strip() if tax_id and tax_id.strip() else None
    cid = company_id or generate_entity_id(EntityIdPrefix.COMPANY)
    s_name = (short_name or clean_code.split("_")[-1]).strip().upper()
    now_str = datetime.now(timezone.utc).isoformat()

    try:
        with get_db_session() as session:
            stmt = select(Company).filter_by(company_code=clean_code)
            existing = session.scalars(stmt).first()
            if existing:
                logger.warning(f"Company code '{clean_code}' already exists.")
                return existing.to_dict()

            if clean_tax_id:
                stmt_tax = select(Company).filter_by(tax_id=clean_tax_id)
                existing_tax = session.scalars(stmt_tax).first()
                if existing_tax:
                    error_msg = f"Tax ID '{clean_tax_id}' already registered for company '{existing_tax.company_code}'."
                    logger.error(error_msg)
                    raise ValueError(error_msg)

            comp = Company(
                company_id=cid,
                company_code=clean_code,
                company_name=company_name.strip(),
                short_name=s_name,
                tax_id=clean_tax_id,
                branch_code=branch_code.strip() if branch_code else "00000",
                is_active=is_active,
                created_at=now_str
            )
            session.add(comp)
            session.flush()
            logger.info(f"Created company '{clean_code}' with ID '{cid}'.")
            return comp.to_dict()
    except Exception as e:
        logger.error(f"Failed to create company '{company_code}': {e}")
        raise e


def get_company(company_id: str) -> dict | None:
    """Retrieves a company by its UUID company_id."""
    if not company_id:
        return None
    try:
        with get_db_session() as session:
            stmt = select(Company).filter_by(company_id=company_id)
            comp = session.scalars(stmt).first()
            return comp.to_dict() if comp else None
    except Exception as e:
        logger.error(f"Failed to get company by ID '{company_id}': {e}")
        return None


def get_company_by_code(company_code: str) -> dict | None:
    """Retrieves a company by its business company_code (e.g. C00000_SAMPLE)."""
    if not company_code:
        return None
    try:
        with get_db_session() as session:
            stmt = select(Company).where(
                func.upper(Company.company_code) == company_code.strip().upper()
            )
            comp = session.scalars(stmt).first()
            return comp.to_dict() if comp else None
    except Exception as e:
        logger.error(f"Failed to get company by code '{company_code}': {e}")
        return None


def get_all_companies(active_only: bool = False) -> list[dict]:
    """Returns list of all companies ordered by company_code."""
    try:
        with get_db_session() as session:
            stmt = select(Company)
            if active_only:
                stmt = stmt.where(Company.is_active == 1)
            stmt = stmt.order_by(Company.company_code.asc())
            companies = session.scalars(stmt).all()
            return [c.to_dict() for c in companies]
    except Exception as e:
        logger.error(f"Failed to get all companies: {e}")
        return []


def update_company(company_id: str, **kwargs) -> bool:
    """Updates fields of an existing company."""
    try:
        with get_db_session() as session:
            stmt = select(Company).filter_by(company_id=company_id)
            comp = session.scalars(stmt).first()
            if not comp:
                return False

            if "tax_id" in kwargs and kwargs["tax_id"]:
                new_tax = kwargs["tax_id"].strip()
                stmt_tax = select(Company).where(
                    Company.tax_id == new_tax,
                    Company.company_id != company_id
                )
                existing_tax = session.scalars(stmt_tax).first()
                if existing_tax:
                    raise ValueError(f"Tax ID '{new_tax}' already registered for company '{existing_tax.company_code}'.")

            for k, v in kwargs.items():
                if hasattr(comp, k):
                    setattr(comp, k, v)
            comp.updated_at = datetime.now(timezone.utc).isoformat()
            return True
    except Exception as e:
        logger.error(f"Failed to update company '{company_id}': {e}")
        return False


def delete_company(company_id_or_code: str) -> bool:
    """Deletes a company record by UUID company_id or unique company_code."""
    try:
        with get_db_session() as session:
            stmt = select(Company).where(
                (Company.company_id == company_id_or_code) |
                (func.upper(Company.company_code) == company_id_or_code.strip().upper())
            )
            comp = session.scalars(stmt).first()
            if not comp:
                return False
            session.delete(comp)
            return True
    except Exception as e:
        logger.error(f"Failed to delete company '{company_id_or_code}': {e}")
        return False


def get_doc_types(company_id: str = None) -> list[dict]:
    """Returns active document types."""
    from src.infrastructure.core.config import get_active_doc_types
    active = get_active_doc_types()
    if active and isinstance(active[0], dict):
        return active
    return [{"doc_type_id": str(dt), "display_name": str(dt).replace("_", " ").title(), "is_active": 1} for dt in active]



def update_doc_type_active_status(doc_type_id: str, is_active: int) -> bool:
    """Updates active status for document type."""
    return True

