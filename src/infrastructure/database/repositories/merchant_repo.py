"""Merchant Gatekeeper and Source repository using Pure SQLAlchemy 2.0 ORM."""

import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import (
    DefaultIdentifier,
    EntityIdPrefix,
    generate_entity_id,
)
from ..engine import get_db_session
from ..models import Company, Merchant, MerchantStatus


def sanitize_short_name(name: str) -> str:
    """
    Cleans raw merchant name to create a safe ASCII short_name and file_prefix identifier.
    Converts special characters to underscores, strips non-ASCII, and lowercases.
    """
    if not name:
        return "merchant"
    cleaned = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)
    cleaned = re.sub(r"[\s-]+", "_", cleaned).strip("_").lower()
    return cleaned if cleaned else "merchant"


def check_short_name_duplicate(short_name: str, company_id: str = None, exclude_merchant_id: str = None) -> bool:
    """Checks if a short_name already exists within the company."""
    if not short_name:
        return False
    try:
        with get_db_session() as session:
            stmt = select(Merchant).where(
                func.lower(Merchant.short_name) == short_name.strip().lower()
            )
            if company_id:
                stmt = stmt.where(Merchant.company_id == company_id)
            if exclude_merchant_id:
                stmt = stmt.where(Merchant.merchant_id != exclude_merchant_id)
            return session.scalars(stmt).first() is not None
    except Exception as e:
        logger.error(f"Failed to check short_name duplicate: {e}")
        return False


def check_file_prefix_duplicate(file_prefix: str, company_id: str = None, exclude_merchant_id: str = None) -> bool:
    """Checks if a file_prefix already exists within the company."""
    if not file_prefix:
        return False
    try:
        with get_db_session() as session:
            stmt = select(Merchant).where(
                func.lower(Merchant.file_prefix) == file_prefix.strip().lower()
            )
            if company_id:
                stmt = stmt.where(Merchant.company_id == company_id)
            if exclude_merchant_id:
                stmt = stmt.where(Merchant.merchant_id != exclude_merchant_id)
            return session.scalars(stmt).first() is not None
    except Exception as e:
        logger.error(f"Failed to check file_prefix duplicate: {e}")
        return False


def match_merchant_by_file_prefix(filename: str, company_id: str = None) -> dict | None:
    """
    Zero-Cost Stage 1 Matching: Matches merchant based on filename prefix matching file_prefix column.
    """
    if not filename:
        return None
    clean_fn = filename.lower()
    try:
        with get_db_session() as session:
            stmt = select(Merchant).where(
                Merchant.is_active == 1
            )
            if company_id:
                stmt = stmt.where(Merchant.company_id == company_id)
            merchants = session.scalars(stmt).all()

            sorted_merchants = sorted(merchants, key=lambda m: len(m.file_prefix or ""), reverse=True)
            for m in sorted_merchants:
                prefix = (m.file_prefix or "").lower()
                if prefix and (clean_fn.startswith(prefix) or f"_{prefix}_" in clean_fn or f"-{prefix}-" in clean_fn or f"_{prefix}." in clean_fn):
                    return m.to_dict()
    except Exception as e:
        logger.error(f"Failed to match merchant by file_prefix for '{filename}': {e}")
    return None


def get_or_create_merchant_auto(
    merchant_name: str = None,
    tax_id: str = None,
    suggested_short_name: str = None,
    company_id: str = None,
    raw_name: str = None,
    **kwargs
) -> tuple[dict, bool]:
    """
    Auto-discovers new merchant during Pipeline execution.
    If already exists (by tax_id or normalized name), returns existing.
    If new, inserts with status_code='PENDING' (Gatekeeper Hold).
    """
    name = (merchant_name or raw_name or "Unknown Merchant").strip()
    clean_name = name if name else "Unknown Merchant"
    clean_tax = tax_id.strip() if tax_id and tax_id.strip() else None
    now_str = datetime.now(timezone.utc).isoformat()

    try:
        with get_db_session() as session:
            target_cid = company_id
            if not target_cid:
                def_comp = session.scalars(select(Company).filter_by(company_code=DefaultIdentifier.COMPANY_CODE)).first()
                if def_comp:
                    target_cid = def_comp.company_id

            if clean_tax:
                stmt = select(Merchant).where(Merchant.tax_id == clean_tax)
                if target_cid:
                    stmt = stmt.where(Merchant.company_id == target_cid)
                existing = session.scalars(stmt).first()
                if existing:
                    return existing.to_dict(), False

            stmt_name = select(Merchant).where(func.lower(Merchant.merchant_name) == clean_name.lower())
            if target_cid:
                stmt_name = stmt_name.where(Merchant.company_id == target_cid)
            existing_name = session.scalars(stmt_name).first()
            if existing_name:
                return existing_name.to_dict(), False

            base_short = suggested_short_name or sanitize_short_name(clean_name)
            candidate_short = base_short
            counter = 1
            while check_short_name_duplicate(candidate_short, company_id=target_cid):
                candidate_short = f"{base_short}_{counter}"
                counter += 1

            mid = generate_entity_id(EntityIdPrefix.MERCHANT)
            new_m = Merchant(
                merchant_id=mid,
                company_id=target_cid,
                tax_id=clean_tax,
                merchant_name=clean_name,
                short_name=candidate_short,
                file_prefix=candidate_short,
                status_code=MerchantStatus.PENDING.value,
                default_wht_rate=0.0,
                is_vat_registered=1,
                is_active=1,
                created_at=now_str
            )
            session.add(new_m)
            session.flush()
            logger.info(f"Auto-discovered new merchant '{clean_name}' (ID: {mid}) -> Gatekeeper status: PENDING")
            return new_m.to_dict(), True
    except Exception as e:
        logger.error(f"Failed in get_or_create_merchant_auto for '{name}': {e}")
        raise


def approve_merchant(
    merchant_id: str,
    approved_by: str,
    short_name: str = None,
    file_prefix: str = None,
    default_wht_rate: float = None,
    is_vat_registered: int = None
) -> tuple[bool, str]:
    """Admin approves a PENDING merchant, unlocking pipeline processing."""
    try:
        with get_db_session() as session:
            stmt = select(Merchant).filter_by(merchant_id=merchant_id)
            m = session.scalars(stmt).first()
            if not m:
                return False, "Merchant not found"

            if short_name and short_name.strip():
                clean_s = short_name.strip().lower()
                if check_short_name_duplicate(clean_s, company_id=m.company_id, exclude_merchant_id=merchant_id):
                    raise ValueError(f"short_name '{clean_s}' already exists in company.")
                m.short_name = clean_s

            if file_prefix and file_prefix.strip():
                clean_p = file_prefix.strip().lower()
                if check_file_prefix_duplicate(clean_p, company_id=m.company_id, exclude_merchant_id=merchant_id):
                    raise ValueError(f"file_prefix '{clean_p}' already exists in company.")
                m.file_prefix = clean_p

            if default_wht_rate is not None:
                m.default_wht_rate = float(default_wht_rate)
            if is_vat_registered is not None:
                m.is_vat_registered = int(is_vat_registered)

            now_str = datetime.now(timezone.utc).isoformat()
            m.status_code = MerchantStatus.APPROVED.value
            m.approved_by = approved_by
            m.approved_at = now_str
            m.updated_at = now_str
            logger.info(f"Merchant '{m.merchant_name}' ({merchant_id}) APPROVED by '{approved_by}'.")
            return True, f"Merchant '{m.merchant_name}' approved successfully"
    except Exception as e:
        logger.error(f"Failed to approve merchant '{merchant_id}': {e}")
        raise


def ignore_merchant(merchant_id: str, approved_by: str) -> tuple[bool, str]:
    """Admin rejects/ignores a merchant. Pipeline will bypass/skip documents from this merchant."""
    try:
        with get_db_session() as session:
            stmt = select(Merchant).filter_by(merchant_id=merchant_id)
            m = session.scalars(stmt).first()
            if not m:
                return False, "Merchant not found"
            now_str = datetime.now(timezone.utc).isoformat()
            m.status_code = MerchantStatus.IGNORED.value
            m.approved_by = approved_by
            m.approved_at = now_str
            m.updated_at = now_str
            logger.info(f"Merchant '{m.merchant_name}' ({merchant_id}) marked IGNORED by '{approved_by}'.")
            return True, f"Merchant '{m.merchant_name}' marked IGNORED"
    except Exception as e:
        logger.error(f"Failed to ignore merchant '{merchant_id}': {e}")
        return False, str(e)


def get_merchants(company_id: str = None, status_code: str = None) -> list[dict]:
    """Returns list of merchants filtered optionally by company_id and status_code."""
    try:
        with get_db_session() as session:
            stmt = select(Merchant)
            if company_id:
                stmt = stmt.where(Merchant.company_id == company_id)
            if status_code:
                stmt = stmt.where(Merchant.status_code == status_code)
            stmt = stmt.order_by(Merchant.merchant_name.asc())
            merchants = session.scalars(stmt).all()
            return [m.to_dict() for m in merchants]
    except Exception as e:
        logger.error(f"Failed to get merchants: {e}")
        return []


def get_pending_merchants(company_id: str = None) -> list[dict]:
    """Returns list of merchants awaiting Admin Gatekeeper review."""
    return get_merchants(company_id=company_id, status_code=MerchantStatus.PENDING.value)


def get_merchant(merchant_id: str) -> dict | None:
    """Retrieves a single merchant by merchant_id."""
    if not merchant_id:
        return None
    try:
        with get_db_session() as session:
            stmt = select(Merchant).filter_by(merchant_id=merchant_id)
            m = session.scalars(stmt).first()
            return m.to_dict() if m else None
    except Exception as e:
        logger.error(f"Failed to get merchant '{merchant_id}': {e}")
        return None


def get_merchant_by_tax_id(tax_id: str, company_id: str = None) -> dict | None:
    """Retrieves a merchant by tax_id."""
    if not tax_id:
        return None
    try:
        with get_db_session() as session:
            stmt = select(Merchant).filter_by(tax_id=tax_id.strip())
            if company_id:
                stmt = stmt.where(Merchant.company_id == company_id)
            m = session.scalars(stmt).first()
            return m.to_dict() if m else None
    except Exception as e:
        logger.error(f"Failed to get merchant by tax ID '{tax_id}': {e}")
        return None


def upsert_merchant(merchant_id: str, company_id: str, merchant_name: str,
                    short_name: str = None, file_prefix: str = None, tax_id: str = None,
                    status_code: str = MerchantStatus.APPROVED.value,
                    default_wht_rate: float = 0.0, is_vat_registered: int = 1,
                    is_active: int = 1, approved_by: str = None) -> dict:
    """Inserts or updates a merchant record using Pure SQLAlchemy 2.0 ORM."""
    clean_name = merchant_name.strip()
    s_name = (short_name or sanitize_short_name(clean_name)).strip().lower()
    prefix = (file_prefix or s_name).strip().lower()
    clean_tax = tax_id.strip() if tax_id and tax_id.strip() else None
    now_str = datetime.now(timezone.utc).isoformat()

    try:
        with get_db_session() as session:
            stmt = select(Merchant).filter_by(merchant_id=merchant_id)
            m = session.scalars(stmt).first()

            if check_short_name_duplicate(s_name, company_id=company_id, exclude_merchant_id=merchant_id):
                raise ValueError(f"short_name '{s_name}' already exists in company.")
            if check_file_prefix_duplicate(prefix, company_id=company_id, exclude_merchant_id=merchant_id):
                raise ValueError(f"file_prefix '{prefix}' already exists in company.")

            if m:
                m.company_id = company_id
                m.merchant_name = clean_name
                m.short_name = s_name
                m.file_prefix = prefix
                m.tax_id = clean_tax
                m.status_code = status_code
                m.default_wht_rate = float(default_wht_rate)
                m.is_vat_registered = int(is_vat_registered)
                m.is_active = int(is_active)
                if approved_by:
                    m.approved_by = approved_by
                    m.approved_at = now_str
                m.updated_at = now_str
            else:
                m = Merchant(
                    merchant_id=merchant_id,
                    company_id=company_id,
                    merchant_name=clean_name,
                    short_name=s_name,
                    file_prefix=prefix,
                    tax_id=clean_tax,
                    status_code=status_code,
                    default_wht_rate=float(default_wht_rate),
                    is_vat_registered=int(is_vat_registered),
                    is_active=int(is_active),
                    approved_by=approved_by,
                    approved_at=now_str if status_code == MerchantStatus.APPROVED.value else None,
                    created_at=now_str
                )
                session.add(m)
            session.flush()
            return m.to_dict()
    except Exception as e:
        logger.error(f"Failed to upsert merchant '{merchant_name}': {e}")
        raise


def match_merchant(tax_id: str = None, merchant_name: str = None, company_id: str = None) -> str | None:
    """
    Standardized merchant lookup using Pure SQLAlchemy 2.0 ORM.
    Returns merchant_id if matched, or None.
    """
    try:
        with get_db_session() as session:
            if tax_id and tax_id.strip():
                clean_tax = tax_id.strip()
                stmt = select(Merchant).where(
                    Merchant.tax_id == clean_tax,
                    Merchant.status_code == MerchantStatus.APPROVED.value
                )
                if company_id:
                    stmt = stmt.where(Merchant.company_id == company_id)
                m = session.scalars(stmt).first()
                if m:
                    return m.merchant_id

            if merchant_name and merchant_name.strip():
                clean_name = merchant_name.strip()
                stmt = select(Merchant).where(
                    func.lower(Merchant.merchant_name) == clean_name.lower(),
                    Merchant.status_code == MerchantStatus.APPROVED.value
                )
                if company_id:
                    stmt = stmt.where(Merchant.company_id == company_id)
                m = session.scalars(stmt).first()
                if m:
                    return m.merchant_id

            if merchant_name and merchant_name.strip():
                clean_name = merchant_name.strip()
                stmt = select(Merchant).where(
                    Merchant.status_code == MerchantStatus.APPROVED.value
                )
                if company_id:
                    stmt = stmt.where(Merchant.company_id == company_id)
                merchants = session.scalars(stmt).all()
                for m in merchants:
                    if m.merchant_name.lower() in clean_name.lower() or clean_name.lower() in m.merchant_name.lower():
                        return m.merchant_id

            return None
    except Exception as e:
        logger.error(f"Failed to match merchant (tax_id: {tax_id}, name: {merchant_name}): {e}")
        return None


def delete_merchant(merchant_id: str) -> bool:
    """Deletes a merchant record."""
    try:
        with get_db_session() as session:
            stmt = select(Merchant).filter_by(merchant_id=merchant_id)
            m = session.scalars(stmt).first()
            if not m:
                return False
            session.delete(m)
            return True
    except Exception as e:
        logger.error(f"Failed to delete merchant '{merchant_id}': {e}")
        return False


def update_merchant_status(merchant_id: str, is_active: int) -> bool:
    """Toggles the is_active status of a merchant."""
    try:
        with get_db_session() as session:
            stmt = select(Merchant).filter_by(merchant_id=merchant_id)
            m = session.scalars(stmt).first()
            if not m:
                return False
            m.is_active = is_active
            m.updated_at = datetime.now(timezone.utc).isoformat()
            return True
    except Exception as e:
        logger.error(f"Failed to update merchant active status '{merchant_id}': {e}")
        return False


def get_sources(doc_type_id: str = None, company_id: str = None) -> list[dict]:
    """Returns list of registered merchants using Pure SQLAlchemy 2.0 ORM."""
    try:
        merchants = get_merchants(company_id=company_id)
        formatted = []
        for m in merchants:
            formatted.append({
                "source_id": m.get("merchant_id") or m.get("short_name"),
                "merchant_id": m.get("merchant_id"),
                "short_name": m.get("short_name"),
                "display_name": m.get("merchant_name"),
                "tax_id": m.get("tax_id"),
                "is_active": m.get("is_active", 1),
                "status_code": m.get("status_code", "APPROVED")
            })
        return formatted
    except Exception as e:
        logger.error(f"Failed to get sources: {e}")
        return []


def update_source_active_status(source_id: str, *args, **kwargs) -> bool:
    """Updates is_active flag for a merchant."""
    is_active = 1
    if args:
        is_active = args[-1]
    elif "is_active" in kwargs:
        is_active = kwargs["is_active"]
    return update_merchant_status(merchant_id=source_id, is_active=int(is_active))
