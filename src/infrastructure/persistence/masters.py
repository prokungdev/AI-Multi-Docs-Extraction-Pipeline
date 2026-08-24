"""Master data and merchant database operations using Pure SQLAlchemy 2.0 ORM."""

import os
import json
import uuid
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from src.infrastructure.common.logger import logger
from sqlalchemy import select, delete, func

from .connection import get_db_session
from .models import (
    Company,
    DocumentSource,
    Merchant,
    MerchantStatus,
    Document,
    ExpenseReceipt,
    ExpenseReceiptItem
)
from src.infrastructure.common.constants import (
    DefaultIdentifier,
    DefaultCompany,
    DefaultPath,
    EntityIdPrefix,
    generate_entity_id,
)


def get_or_create_default_company() -> dict:
    """
    Ensures default sandbox company exists and returns its dictionary representation.
    """
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
    """
    Creates a new client company entity in the database.
    """
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
    """
    Retrieves a company by its UUID company_id.
    """
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
    """
    Retrieves a company by its business company_code (e.g. C00000_SAMPLE).
    """
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
    """
    Returns list of all companies ordered by company_code.
    """
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
    """
    Updates fields of an existing company.
    """
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
    """
    Deletes a company record by UUID company_id or unique company_code.
    Pure SQLAlchemy 2.0 pattern.
    """
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


def get_doc_types(settings_path: str = DefaultPath.SETTINGS) -> list[dict]:
    """
    Returns list of doc_types from configs/settings.json.
    """
    if not os.path.exists(settings_path):
        logger.warning(f"Settings configuration file not found at: {settings_path}")
        return []
    try:
        from src.infrastructure.common.config_loader import load_system_settings
        settings = load_system_settings(settings_path)
        doc_types = settings.get("doc_types") or settings.get("domains", [])
        formatted_doc_types = []
        for d in doc_types:
            d_id = d.get("doc_type_id") or d.get("domain_id")
            if d_id:
                formatted_doc_types.append({
                    "doc_type_id": d_id,
                    "domain_id": d_id,
                    "display_name": d.get("display_name", d_id),
                    "is_active": 1 if d.get("is_active", True) else 0,
                    "sort_order": d.get("sort_order", 0)
                })
        formatted_doc_types.sort(key=lambda x: x["sort_order"])
        return formatted_doc_types
    except Exception as e:
        logger.error(f"Failed to load doc_types from settings.json: {e}")
        return []




def get_sources(doc_type_id: str) -> list[dict]:
    """
    Returns list of sources for a doc_type from database using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            stmt = select(DocumentSource).where(DocumentSource.doc_type_id == doc_type_id)
            sources = session.scalars(stmt).all()
            return [s.to_dict() for s in sources]
    except Exception as e:
        logger.error(f"Failed to load sources for doc_type '{doc_type_id}': {e}")
        return []


def update_doc_type_active_status(doc_type_id: str, is_active: int, settings_path: str = DefaultPath.SETTINGS) -> bool:
    """
    Updates the is_active status of a doc_type in settings.json.
    """
    try:
        if not os.path.exists(settings_path):
            return False
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        doc_types = settings.get("doc_types") or settings.get("domains", [])
        for d in doc_types:
            if d.get("doc_type_id") == doc_type_id or d.get("domain_id") == doc_type_id:
                d["is_active"] = bool(is_active)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to update doc_type active status: {e}")
        return False




def update_source_active_status(source_id: str, doc_type_id: str, is_active: int) -> bool:
    """
    Updates the is_active status of a source using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            stmt = select(DocumentSource).filter_by(source_id=source_id, doc_type_id=doc_type_id)
            src = session.scalars(stmt).first()
            if src:
                src.is_active = is_active
                return True
            return False
    except Exception as e:
        logger.error(f"Failed to update source active status: {e}")
        return False




from src.domain.services.classifier import sanitize_short_name


def get_merchants(company_id: str = None) -> list[dict]:
    """
    Retrieves all merchants from database using Pure SQLAlchemy 2.0 ORM.
    Optionally filters by company_id.
    """
    try:
        with get_db_session() as session:
            stmt = select(Merchant)
            if company_id:
                stmt = stmt.where(Merchant.company_id == company_id)
            stmt = stmt.order_by(Merchant.merchant_name.asc())
            merchants = session.scalars(stmt).all()
            return [m.to_dict() for m in merchants]
    except Exception as e:
        logger.error(f"Failed to get merchants: {e}")
        return []




def get_pending_merchants(company_id: str = None) -> list[dict]:
    """
    Retrieves all merchants that are in 'PENDING' status waiting for review.
    Optionally filters by company_id.
    """
    try:
        with get_db_session() as session:
            stmt = select(Merchant).where(
                Merchant.status_code == MerchantStatus.PENDING.value
            )
            if company_id:
                stmt = stmt.where(Merchant.company_id == company_id)
            stmt = stmt.order_by(Merchant.created_at.desc())
            merchants = session.scalars(stmt).all()
            return [m.to_dict() for m in merchants]
    except Exception as e:
        logger.error(f"Failed to get pending merchants: {e}")
        return []


def get_merchant_by_tax_id(tax_id: str, company_id: str = None) -> dict | None:
    """
    Finds a merchant record by its 13-digit Tax ID using Pure SQLAlchemy 2.0 ORM.
    Optionally filters by company_id.
    """
    if not tax_id or not tax_id.strip():
        return None
    try:
        with get_db_session() as session:
            stmt = select(Merchant).where(
                Merchant.tax_id == tax_id.strip()
            )
            if company_id:
                stmt = stmt.where(Merchant.company_id == company_id)
            merchant = session.scalars(stmt).first()
            return merchant.to_dict() if merchant else None
    except Exception as e:
        logger.error(f"Failed to get merchant by tax_id '{tax_id}': {e}")
        return None


def check_short_name_duplicate(short_name: str, exclude_merchant_id: str = None, company_id: str = None) -> bool:
    """
    Checks if short_name already exists in merchants table for another merchant.
    """
    if not short_name or not short_name.strip():
        return False
    try:
        with get_db_session() as session:
            stmt = select(Merchant.merchant_id).where(
                func.lower(Merchant.short_name) == short_name.strip().lower()
            )
            if exclude_merchant_id:
                stmt = stmt.where(Merchant.merchant_id != exclude_merchant_id)
            if company_id:
                stmt = stmt.where(Merchant.company_id == company_id)
            return session.scalars(stmt).first() is not None
    except Exception as e:
        logger.error(f"Error checking duplicate short_name: {e}")
        return False


def check_file_prefix_duplicate(file_prefix: str, exclude_merchant_id: str = None, company_id: str = None) -> bool:
    """
    Checks if file_prefix already exists in merchants table for another merchant.
    """
    if not file_prefix or not file_prefix.strip():
        return False
    try:
        with get_db_session() as session:
            stmt = select(Merchant.merchant_id).where(
                func.lower(Merchant.file_prefix) == file_prefix.strip().lower()
            )
            if exclude_merchant_id:
                stmt = stmt.where(Merchant.merchant_id != exclude_merchant_id)
            if company_id:
                stmt = stmt.where(Merchant.company_id == company_id)
            return session.scalars(stmt).first() is not None
    except Exception as e:
        logger.error(f"Error checking duplicate file_prefix: {e}")
        return False


def match_merchant_by_file_prefix(filename: str, company_id: str = None) -> dict | None:
    """
    Matches a document filename against active merchant file_prefix rules.
    If the filename starts with or contains '{file_prefix}_', returns the matched merchant dict.
    """
    if not filename or not filename.strip():
        return None
    try:
        clean_name = os.path.basename(filename).strip().lower()
        with get_db_session() as session:
            stmt = select(Merchant).where(
                Merchant.file_prefix.isnot(None),
                Merchant.file_prefix != ""
            )
            if company_id:
                stmt = stmt.where(Merchant.company_id == company_id)
            merchants = session.scalars(stmt).all()

            # Sort by longest prefix first to prioritize specific matches
            sorted_merchants = sorted(
                merchants,
                key=lambda m: len(m.file_prefix or ""),
                reverse=True
            )

            for m in sorted_merchants:
                prefix = m.file_prefix.strip().lower()
                if not prefix or prefix == "merchant":
                    continue
                if clean_name.startswith(f"{prefix}_") or f"_{prefix}_" in clean_name:
                    return m.to_dict()
    except Exception as e:
        logger.error(f"Error matching merchant by file prefix: {e}")
    return None


def get_or_create_merchant_auto(
    tax_id: str,
    merchant_name: str,
    suggested_short_name: str = None,
    domain_id: str = "expense_receipt",
    company_id: str = None
) -> tuple[dict, bool]:
    """
    Matches or creates a merchant in PENDING status using Pure SQLAlchemy 2.0 ORM.
    Returns:
        tuple (merchant_dict, is_new_created)
    """
    now_str = datetime.now(timezone.utc).isoformat()
    clean_tax_id = tax_id.strip() if tax_id and tax_id.strip() else None
    clean_name = merchant_name.strip() if merchant_name and merchant_name.strip() else "Unknown Merchant"

    try:
        with get_db_session() as session:
            # Fallback to default company if company_id is None
            target_company_id = company_id
            if not target_company_id:
                def_comp = session.scalars(select(Company).filter_by(company_code=DefaultIdentifier.COMPANY_CODE)).first()
                if def_comp:
                    target_company_id = def_comp.company_id

            # 1. Match by Tax ID first
            if clean_tax_id:
                stmt_tax = select(Merchant).filter_by(tax_id=clean_tax_id)
                if target_company_id:
                    stmt_tax = stmt_tax.where(Merchant.company_id == target_company_id)
                existing = session.scalars(stmt_tax).first()
                if existing:
                    return existing.to_dict(), False

            # 2. Match by Merchant Name (exact case-insensitive)
            stmt_name = select(Merchant).where(
                func.lower(Merchant.merchant_name) == clean_name.lower()
            )
            if target_company_id:
                stmt_name = stmt_name.where(Merchant.company_id == target_company_id)
            existing = session.scalars(stmt_name).first()
            if existing:
                return existing.to_dict(), False

            # 3. Create new merchant in PENDING status
            merchant_id = generate_entity_id(EntityIdPrefix.MERCHANT)
            raw_short_name = suggested_short_name or sanitize_short_name(clean_name)
            base_short_name = raw_short_name
            candidate_short_name = base_short_name
            counter = 2
            while check_short_name_duplicate(candidate_short_name, company_id=target_company_id):
                candidate_short_name = f"{base_short_name}_{counter}"
                counter += 1

            new_merchant = Merchant(
                merchant_id=merchant_id,
                company_id=target_company_id,
                tax_id=clean_tax_id,
                merchant_name=clean_name,
                short_name=candidate_short_name,
                file_prefix=candidate_short_name,
                status_code=MerchantStatus.PENDING.value,
                approved_by=None,
                approved_at=None,
                default_wht_rate=0.0,
                is_vat_registered=1,
                created_at=now_str
            )
            session.add(new_merchant)
            session.flush()
            logger.info(f"Auto-created new merchant in PENDING status: '{clean_name}' (Tax ID: {clean_tax_id}, short_name: {candidate_short_name})")
            return new_merchant.to_dict(), True
    except Exception as e:
        logger.error(f"Failed in get_or_create_merchant_auto for '{merchant_name}': {e}")
        return {
            "merchant_id": generate_entity_id(EntityIdPrefix.MERCHANT),
            "company_id": company_id,
            "tax_id": clean_tax_id,
            "merchant_name": clean_name,
            "short_name": DefaultIdentifier.DEFAULT_SHORT_NAME,
            "file_prefix": DefaultIdentifier.DEFAULT_SHORT_NAME,
            "status_code": MerchantStatus.PENDING.value,
            "created_at": now_str
        }, True


def approve_merchant(merchant_id: str, short_name: str = None, file_prefix: str = None,
                     approved_by: str = "admin", doc_type_id: str = "expense_receipt") -> tuple[bool, str]:
    """
    Approves a merchant from PENDING to APPROVED status.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    try:
        with get_db_session() as session:
            stmt = select(Merchant).filter_by(merchant_id=merchant_id)
            merchant = session.scalars(stmt).first()
            if not merchant:
                return False, f"Merchant ID '{merchant_id}' not found."

            final_short_name = (short_name or merchant.short_name or sanitize_short_name(merchant.merchant_name)).strip().lower()
            if not final_short_name:
                final_short_name = "merchant"

            final_prefix = (file_prefix or merchant.file_prefix or final_short_name).strip().lower()
            if not final_prefix:
                final_prefix = final_short_name

            if check_short_name_duplicate(final_short_name, exclude_merchant_id=merchant_id, company_id=merchant.company_id):
                return False, f"Short name '{final_short_name}' is already used by another merchant."

            if check_file_prefix_duplicate(final_prefix, exclude_merchant_id=merchant_id, company_id=merchant.company_id):
                return False, f"File prefix '{final_prefix}' is already used by another merchant."

            merchant.short_name = final_short_name
            merchant.file_prefix = final_prefix
            merchant.status_code = MerchantStatus.APPROVED.value
            merchant.approved_by = approved_by
            merchant.approved_at = now_str
            merchant.updated_at = now_str

            logger.info(f"Merchant '{merchant_id}' ({merchant.merchant_name}) approved with prefix '{final_prefix}'.")
            return True, f"Merchant '{merchant.merchant_name}' approved successfully."
    except Exception as e:
        logger.error(f"Failed to approve merchant '{merchant_id}': {e}")
        return False, str(e)


def ignore_merchant(merchant_id: str, approved_by: str = "admin") -> tuple[bool, str]:
    """
    Marks a merchant as IGNORED.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    try:
        with get_db_session() as session:
            stmt = select(Merchant).filter_by(merchant_id=merchant_id)
            merchant = session.scalars(stmt).first()
            if not merchant:
                return False, f"Merchant ID '{merchant_id}' not found."

            merchant.status_code = MerchantStatus.IGNORED.value
            merchant.approved_by = approved_by
            merchant.approved_at = now_str
            merchant.updated_at = now_str

            logger.info(f"Merchant '{merchant_id}' marked as IGNORED by '{approved_by}'.")
            return True, f"Merchant '{merchant.merchant_name}' set to IGNORED."
    except Exception as e:
        logger.error(f"Failed to ignore merchant '{merchant_id}': {e}")
        return False, str(e)


def upsert_merchant(merchant_data: dict) -> bool:
    """
    Inserts or updates a merchant record in merchants table using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            m_id = merchant_data.get("merchant_id")
            if not m_id:
                m_id = generate_entity_id(EntityIdPrefix.MERCHANT)

            stmt = select(Merchant).filter_by(merchant_id=m_id)
            merchant = session.scalars(stmt).first()
            now_str = datetime.now(timezone.utc).isoformat()
            target_cid = merchant_data.get("company_id")

            if merchant:
                if target_cid:
                    merchant.company_id = target_cid
                merchant.tax_id = merchant_data.get("tax_id", merchant.tax_id)
                merchant.merchant_name = merchant_data.get("merchant_name", merchant.merchant_name)
                merchant.short_name = merchant_data.get("short_name", merchant.short_name)
                merchant.file_prefix = merchant_data.get("file_prefix", merchant.file_prefix)
                merchant.status_code = merchant_data.get("status_code", merchant.status_code)
                merchant.approved_by = merchant_data.get("approved_by", merchant.approved_by)
                merchant.approved_at = merchant_data.get("approved_at", merchant.approved_at)
                merchant.default_wht_rate = float(merchant_data.get("default_wht_rate", merchant.default_wht_rate))
                merchant.is_vat_registered = int(merchant_data.get("is_vat_registered", merchant.is_vat_registered))
                merchant.updated_at = now_str
            else:
                if not target_cid:
                    def_comp = session.scalars(select(Company).filter_by(company_code=DefaultIdentifier.COMPANY_CODE)).first()
                    if def_comp:
                        target_cid = def_comp.company_id

                new_m = Merchant(
                    merchant_id=m_id,
                    company_id=target_cid,
                    tax_id=merchant_data.get("tax_id"),
                    merchant_name=merchant_data.get("merchant_name", "Unknown Merchant"),
                    short_name=merchant_data.get("short_name", "merchant"),
                    file_prefix=merchant_data.get("file_prefix", "merchant"),
                    status_code=merchant_data.get("status_code", MerchantStatus.APPROVED.value),
                    approved_by=merchant_data.get("approved_by"),
                    approved_at=merchant_data.get("approved_at"),
                    default_wht_rate=float(merchant_data.get("default_wht_rate", 0.0)),
                    is_vat_registered=int(merchant_data.get("is_vat_registered", 1)),
                    created_at=merchant_data.get("created_at", now_str)
                )
                session.add(new_m)
            return True
    except Exception as e:
        logger.error(f"Failed to upsert merchant: {e}")
        return False


def match_merchant(tax_id: str, name: str, company_id: str = None) -> str | None:
    """
    Matches a merchant from merchants by tax_id first, then by merchant_name using Pure SQLAlchemy 2.0 ORM.
    Returns merchant_id if matched, otherwise None.
    """
    try:
        with get_db_session() as session:
            # 1. Match by Tax ID (exact match)
            if tax_id and tax_id.strip():
                stmt = select(Merchant).filter_by(tax_id=tax_id.strip())
                if company_id:
                    stmt = stmt.where(Merchant.company_id == company_id)
                merchant = session.scalars(stmt).first()
                if merchant:
                    return merchant.merchant_id

            # 2. Match by Merchant Name (case-insensitive match)
            if name and name.strip():
                stmt = select(Merchant).where(
                    func.lower(Merchant.merchant_name) == name.strip().lower()
                )
                if company_id:
                    stmt = stmt.where(Merchant.company_id == company_id)
                merchant = session.scalars(stmt).first()
                if merchant:
                    return merchant.merchant_id
    except Exception as e:
        logger.error(f"Error matching merchant: {e}")
    return None


def delete_merchant(merchant_id: str) -> bool:
    """
    Deletes a merchant record from merchants using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            stmt = select(Merchant).filter_by(merchant_id=merchant_id)
            merchant = session.scalars(stmt).first()
            if merchant:
                session.delete(merchant)
                return True
            return False
    except Exception as e:
        logger.error(f"Failed to delete merchant '{merchant_id}': {e}")
        return False


def insert_relational_receipt(document_id: str, payload: dict, original_filename: str, company_id: str = None) -> bool:
    """
    Parses extracted JSON payload and inserts header and items into relational tables using Pure SQLAlchemy 2.0 ORM.
    Also auto-registers new merchants in merchants table.
    """
    try:
        with get_db_session() as session:
            now_str = datetime.now(timezone.utc).isoformat()

            # Target company resolution
            target_cid = company_id
            if not target_cid:
                doc = session.scalars(select(Document).filter_by(document_id=document_id)).first()
                if doc and doc.company_id:
                    target_cid = doc.company_id
                else:
                    def_comp = session.scalars(select(Company).filter_by(company_code=DefaultIdentifier.COMPANY_CODE)).first()
                    if def_comp:
                        target_cid = def_comp.company_id

            # 1. Extract merchant & receipt information with fallbacks
            merchant_obj = payload.get("merchant", {})
            receipt_info = payload.get("receipt_info", {})
            totals_obj = payload.get("totals", {}) or payload.get("financial_summary", {})

            merchant_name = merchant_obj.get("name") or payload.get("merchant_name") or "Unknown Merchant"
            tax_id = merchant_obj.get("tax_id") or payload.get("tax_id")
            if tax_id:
                tax_id = tax_id.strip()

            # 2. Match merchant in merchants
            merchant_id = match_merchant(tax_id, merchant_name, company_id=target_cid)
            if not merchant_id:
                merchant_id = generate_entity_id(EntityIdPrefix.MERCHANT)
                short_name = sanitize_short_name(merchant_name)
                new_m = Merchant(
                    merchant_id=merchant_id,
                    company_id=target_cid,
                    tax_id=tax_id,
                    merchant_name=merchant_name,
                    short_name=short_name,
                    file_prefix=short_name,
                    status_code=MerchantStatus.APPROVED.value,
                    default_wht_rate=0.0,
                    is_vat_registered=1,
                    created_at=now_str
                )
                session.add(new_m)
                session.flush()

            # 3. Clean up any existing receipt for this document_id (updates/re-runs)
            existing_receipts = session.scalars(select(ExpenseReceipt).filter_by(document_id=document_id)).all()
            for r in existing_receipts:
                session.delete(r)
            session.flush()

            receipt_id = generate_entity_id(EntityIdPrefix.RECEIPT)

            # 4. Save Header
            subtotal = totals_obj.get("subtotal", 0.0)
            discount = totals_obj.get("discount", 0.0)
            vat_amount = totals_obj.get("vat_amount", 0.0)
            net_amount = totals_obj.get("net_amount", 0.0)

            transaction_date = receipt_info.get("transaction_date") or payload.get("transaction_date")
            expense_category = receipt_info.get("expense_category") or payload.get("expense_category")
            payment_method = receipt_info.get("payment_method") or payload.get("payment_method")

            receipt = ExpenseReceipt(
                receipt_id=receipt_id,
                company_id=target_cid,
                document_id=document_id,
                merchant_id=merchant_id,
                transaction_date=transaction_date,
                merchant_name=merchant_name,
                tax_id=tax_id,
                expense_category=expense_category,
                subtotal=subtotal,
                discount_amount=discount,
                vat_amount=vat_amount,
                net_amount=net_amount,
                payment_method=payment_method,
                source_filename=original_filename,
                created_at=now_str
            )
            session.add(receipt)
            session.flush()

            # 5. Save Details (line items)
            for item in payload.get("items", []):
                item_name = item.get("name")
                if not item_name:
                    continue
                qty = item.get("quantity") or item.get("qty", 1.0)
                unit_price = item.get("unit_price", 0.0)
                total_price = item.get("total_price", 0.0)

                detail_item = ExpenseReceiptItem(
                    item_id=generate_entity_id(EntityIdPrefix.ITEM),
                    receipt_id=receipt_id,
                    item_name=item_name,
                    quantity=float(qty),
                    unit_price=float(unit_price),
                    total_price=float(total_price)
                )
                session.add(detail_item)

            return True
    except Exception as e:
        logger.error(f"Failed to insert relational receipt for doc '{document_id}': {e}")
        return False


from .models import User
from src.infrastructure.common.constants import UserRole


def create_user(
    email: str,
    full_name: str,
    role: str = UserRole.ADMIN.value,
    company_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> dict:
    """
    Creates a new user entity in the database with fail-fast uniqueness validation.
    """
    clean_email = email.strip().lower()
    clean_name = full_name.strip()
    clean_role = role.strip().upper() if role else UserRole.ADMIN.value
    uid = user_id or generate_entity_id(EntityIdPrefix.USER)
    now_str = datetime.now(timezone.utc).isoformat()

    try:
        with get_db_session() as session:
            stmt = select(User).filter_by(email=clean_email)
            existing = session.scalars(stmt).first()
            if existing:
                error_msg = f"User with email '{clean_email}' already exists."
                logger.error(error_msg)
                raise ValueError(error_msg)

            new_user = User(
                user_id=uid,
                company_id=company_id,
                email=clean_email,
                full_name=clean_name,
                role=clean_role,
                is_active=1,
                created_at=now_str
            )
            session.add(new_user)
            session.flush()
            logger.info(f"Created user '{clean_email}' with ID '{uid}' (Role: {clean_role}).")
            return new_user.to_dict()
    except Exception as e:
        logger.error(f"Failed to create user '{clean_email}': {e}")
        raise


def get_user_by_id(user_id: str) -> Optional[dict]:
    """Retrieves a user entity dictionary by user_id."""
    try:
        with get_db_session() as session:
            stmt = select(User).filter_by(user_id=user_id.strip())
            user = session.scalars(stmt).first()
            return user.to_dict() if user else None
    except Exception as e:
        logger.error(f"Failed to get user by ID '{user_id}': {e}")
        return None


def get_user_by_email(email: str) -> Optional[dict]:
    """Retrieves a user entity dictionary by email."""
    try:
        with get_db_session() as session:
            stmt = select(User).filter_by(email=email.strip().lower())
            user = session.scalars(stmt).first()
            return user.to_dict() if user else None
    except Exception as e:
        logger.error(f"Failed to get user by email '{email}': {e}")
        return None


def list_users(company_id: Optional[str] = None) -> list[dict]:
    """Lists users optionally filtered by company_id."""
    try:
        with get_db_session() as session:
            stmt = select(User)
            if company_id:
                stmt = stmt.filter_by(company_id=company_id)
            users = session.scalars(stmt).all()
            return [u.to_dict() for u in users]
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        return []
