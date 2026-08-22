"""Master data and merchant database operations using SQLAlchemy 2.0 ORM."""

import os
import json
import uuid
import re
from datetime import datetime, timezone
from loguru import logger
from sqlalchemy import func

from .connection import get_db_session
from .models import (
    DocumentSource,
    ApiCredential,
    Merchant,
    MerchantStatus,
    ExpenseReceipt,
    ExpenseReceiptItem
)


def get_domains(settings_path: str = "configs/settings.json") -> list[dict]:
    """
    Returns list of doc_types/domains from configs/settings.json.
    """
    if not os.path.exists(settings_path):
        logger.warning(f"Settings configuration file not found at: {settings_path}")
        return []
    try:
        from src.core.config_loader import load_system_settings
        settings = load_system_settings(settings_path)
        domains = settings.get("doc_types") or settings.get("domains", [])
        formatted_domains = []
        for d in domains:
            d_id = d.get("doc_type_id") or d.get("domain_id")
            if d_id:
                formatted_domains.append({
                    "domain_id": d_id,
                    "doc_type_id": d_id,
                    "display_name": d.get("display_name", d_id),
                    "is_active": 1 if d.get("is_active", True) else 0,
                    "sort_order": d.get("sort_order", 0)
                })
        formatted_domains.sort(key=lambda x: x["sort_order"])
        return formatted_domains
    except Exception as e:
        logger.error(f"Failed to load doc_types/domains from settings.json: {e}")
        return []


def get_sources(domain_id: str) -> list[dict]:
    """
    Returns list of sources for a domain from database using SQLAlchemy ORM.
    """
    try:
        with get_db_session() as session:
            sources = session.query(DocumentSource).filter(DocumentSource.domain_id == domain_id).all()
            return [s.to_dict() for s in sources]
    except Exception as e:
        logger.error(f"Failed to load sources for domain '{domain_id}': {e}")
        return []


def update_domain_active_status(domain_id: str, is_active: int, settings_path: str = "configs/settings.json") -> bool:
    """
    Toggles is_active for a domain inside configs/settings.json and clears the settings cache.
    """
    if not os.path.exists(settings_path):
        logger.error(f"Settings configuration file not found at: {settings_path}")
        return False
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)

        domains = settings.get("domains", [])
        updated = False
        for d in domains:
            if d.get("domain_id") == domain_id:
                d["is_active"] = True if is_active == 1 else False
                updated = True
                break

        if updated:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            try:
                from src.core.config_loader import load_system_settings
                load_system_settings.cache_clear()
            except Exception:
                pass
            logger.info(f"Updated domain '{domain_id}' active status to {is_active == 1} in {settings_path}")
            return True
        else:
            logger.warning(f"Domain '{domain_id}' not found in {settings_path}")
            return False
    except Exception as e:
        logger.error(f"Failed to update domain active status in {settings_path}: {e}")
        return False


def update_source_active_status(source_id: str, domain_id: str, is_active: int) -> bool:
    """
    Updates the is_active status of a source in document_sources table using SQLAlchemy ORM.
    """
    try:
        with get_db_session() as session:
            src = session.query(DocumentSource).filter_by(source_id=source_id, domain_id=domain_id).first()
            if src:
                src.is_active = is_active
                logger.info(f"Updated source '{source_id}' ({domain_id}) active status to {is_active}")
                return True
            else:
                logger.warning(f"Source '{source_id}' not found for domain '{domain_id}'")
                return False
    except Exception as e:
        logger.error(f"Failed to update source active status for '{source_id}': {e}")
        return False


def get_active_credentials() -> list[dict]:
    """
    Retrieves all active API credentials ordered by error_count asc, last_active_at asc.
    """
    try:
        with get_db_session() as session:
            creds = session.query(ApiCredential).filter(
                ApiCredential.is_active == 1
            ).order_by(
                ApiCredential.error_count.asc(),
                ApiCredential.last_active_at.asc()
            ).all()
            return [c.to_dict() for c in creds]
    except Exception as e:
        logger.error(f"Failed to get active credentials: {e}")
        return []


def update_credential_status(credential_id: str, last_active_at: str = None, error_count: int = None, is_active: int = None) -> bool:
    """
    Updates status, error_count, and last_active_at timestamp for a credential using SQLAlchemy ORM.
    """
    try:
        with get_db_session() as session:
            cred = session.query(ApiCredential).filter_by(credential_id=credential_id).first()
            if not cred:
                return False
            if last_active_at is not None:
                cred.last_active_at = last_active_at
            if error_count is not None:
                cred.error_count = error_count
            if is_active is not None:
                cred.is_active = is_active
            return True
    except Exception as e:
        logger.error(f"Failed to update credential status for '{credential_id}': {e}")
        return False


def sanitize_short_name(name: str) -> str:
    """
    Sanitizes a merchant name or identifier into a filesystem-safe short_name.
    Converts to lowercase, removes stop words, replaces non-alphanumeric with underscore.
    """
    if not name:
        return "merchant"
    clean = name.lower()
    for stop_word in [
        "บริษัท", "จำกัด", "มหาชน", "ห้างหุ้นส่วนจำกัด", "หจก", "บจก",
        "company", "limited", "co., ltd.", "co.,ltd.", "co.,ltd", "corp", "inc"
    ]:
        clean = clean.replace(stop_word, " ")
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", clean)
    clean = re.sub(r"_+", "_", clean).strip("_")
    if not clean:
        clean = "merchant"
    return clean[:40]


def get_merchants() -> list[dict]:
    """
    Retrieves all merchants from merchants table using SQLAlchemy ORM.
    """
    try:
        with get_db_session() as session:
            merchants = session.query(Merchant).order_by(Merchant.merchant_name.asc()).all()
            return [m.to_dict() for m in merchants]
    except Exception as e:
        logger.error(f"Failed to get merchants: {e}")
        return []


def get_all_merchants() -> list[dict]:
    """
    Alias for get_merchants().
    """
    return get_merchants()


def get_pending_merchants() -> list[dict]:
    """
    Retrieves all merchants that are in 'PENDING' status waiting for review.
    """
    try:
        with get_db_session() as session:
            merchants = session.query(Merchant).filter(
                Merchant.status_code == MerchantStatus.PENDING.value
            ).order_by(Merchant.created_at.desc()).all()
            return [m.to_dict() for m in merchants]
    except Exception as e:
        logger.error(f"Failed to get pending merchants: {e}")
        return []


def get_merchant_by_tax_id(tax_id: str) -> dict | None:
    """
    Finds a merchant record by its 13-digit Tax ID using SQLAlchemy ORM.
    """
    if not tax_id or not tax_id.strip():
        return None
    try:
        with get_db_session() as session:
            merchant = session.query(Merchant).filter(
                Merchant.tax_id == tax_id.strip()
            ).first()
            return merchant.to_dict() if merchant else None
    except Exception as e:
        logger.error(f"Failed to get merchant by tax_id '{tax_id}': {e}")
        return None


def check_short_name_duplicate(short_name: str, exclude_merchant_id: str = None) -> bool:
    """
    Checks if short_name already exists in merchants table for another merchant.
    """
    if not short_name or not short_name.strip():
        return False
    try:
        with get_db_session() as session:
            query = session.query(Merchant.merchant_id).filter(
                func.lower(Merchant.short_name) == short_name.strip().lower()
            )
            if exclude_merchant_id:
                query = query.filter(Merchant.merchant_id != exclude_merchant_id)
            return query.first() is not None
    except Exception as e:
        logger.error(f"Error checking duplicate short_name: {e}")
        return False


def check_file_prefix_duplicate(file_prefix: str, exclude_merchant_id: str = None) -> bool:
    """
    Checks if file_prefix already exists in merchants table for another merchant.
    """
    if not file_prefix or not file_prefix.strip():
        return False
    try:
        with get_db_session() as session:
            query = session.query(Merchant.merchant_id).filter(
                func.lower(Merchant.file_prefix) == file_prefix.strip().lower()
            )
            if exclude_merchant_id:
                query = query.filter(Merchant.merchant_id != exclude_merchant_id)
            return query.first() is not None
    except Exception as e:
        logger.error(f"Error checking duplicate file_prefix: {e}")
        return False


def match_merchant_by_file_prefix(filename: str) -> dict | None:
    """
    Matches a document filename against active merchant file_prefix rules.
    If the filename starts with or contains '{file_prefix}_', returns the matched merchant dict.
    """
    if not filename or not filename.strip():
        return None
    try:
        clean_name = os.path.basename(filename).strip().lower()
        with get_db_session() as session:
            merchants = session.query(Merchant).filter(
                Merchant.file_prefix.isnot(None),
                Merchant.file_prefix != ""
            ).all()

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

                if clean_name.startswith(f"{prefix}_") or clean_name.startswith(f"{prefix}-") or clean_name.startswith(f"{prefix}."):
                    logger.info(f"Zero-cost rule match: '{filename}' matched file_prefix '{prefix}' for merchant '{m.merchant_name}'.")
                    return m.to_dict()

            return None
    except Exception as e:
        logger.error(f"Error matching merchant by file_prefix for '{filename}': {e}")
        return None


def get_or_create_merchant_auto(tax_id: str, merchant_name: str, suggested_short_name: str = None) -> tuple[dict, bool]:
    """
    Gatekeeper logic for auto-registering merchants.
    If tax_id exists, reuses existing merchant directly without duplicate suffix.
    If new, registers in PENDING status.
    Returns:
        tuple (merchant_dict, is_newly_created_boolean)
    """
    now_str = datetime.now(timezone.utc).isoformat()
    clean_tax_id = tax_id.strip() if tax_id and tax_id.strip() else None
    clean_name = merchant_name.strip() if merchant_name and merchant_name.strip() else "Unknown Merchant"

    try:
        with get_db_session() as session:
            # 1. Match by Tax ID first
            if clean_tax_id:
                existing = session.query(Merchant).filter_by(tax_id=clean_tax_id).first()
                if existing:
                    return existing.to_dict(), False

            # 2. Match by Merchant Name (exact case-insensitive)
            existing = session.query(Merchant).filter(
                func.lower(Merchant.merchant_name) == clean_name.lower()
            ).first()
            if existing:
                return existing.to_dict(), False

            # 3. Create new merchant in PENDING status
            merchant_id = f"merch_{uuid.uuid4().hex[:8]}"
            raw_short_name = suggested_short_name or sanitize_short_name(clean_name)
            base_short_name = raw_short_name
            candidate_short_name = base_short_name
            counter = 2
            while check_short_name_duplicate(candidate_short_name):
                candidate_short_name = f"{base_short_name}_{counter}"
                counter += 1

            new_merchant = Merchant(
                merchant_id=merchant_id,
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
            "merchant_id": f"merch_fallback_{uuid.uuid4().hex[:6]}",
            "tax_id": clean_tax_id,
            "merchant_name": clean_name,
            "short_name": "merchant",
            "file_prefix": "merchant",
            "status_code": MerchantStatus.PENDING.value,
            "created_at": now_str
        }, True


def approve_merchant(merchant_id: str, short_name: str = None, file_prefix: str = None,
                     approved_by: str = "admin", doc_type_id: str = "expense_receipt") -> tuple[bool, str]:
    """
    Approves a merchant from PENDING to APPROVED status.
    Returns:
        tuple (success_boolean, message)
    """
    now_str = datetime.now(timezone.utc).isoformat()
    try:
        with get_db_session() as session:
            merchant = session.query(Merchant).filter_by(merchant_id=merchant_id).first()
            if not merchant:
                return False, f"Merchant ID '{merchant_id}' not found."

            final_short_name = (short_name or merchant.short_name or sanitize_short_name(merchant.merchant_name)).strip().lower()
            if not final_short_name:
                final_short_name = "merchant"

            final_prefix = (file_prefix or merchant.file_prefix or final_short_name).strip().lower()
            if not final_prefix:
                final_prefix = final_short_name

            if check_short_name_duplicate(final_short_name, exclude_merchant_id=merchant_id):
                return False, f"Short name '{final_short_name}' is already used by another merchant."

            if check_file_prefix_duplicate(final_prefix, exclude_merchant_id=merchant_id):
                return False, f"File prefix '{final_prefix}' is already used by another merchant."

            old_short_name = merchant.short_name
            tax_id = merchant.tax_id or "NO_TAXID"

            merchant.short_name = final_short_name
            merchant.file_prefix = final_prefix
            merchant.status_code = MerchantStatus.APPROVED.value
            merchant.approved_by = approved_by
            merchant.approved_at = now_str
            merchant.updated_at = now_str

            # Update filesystem folder structure
            try:
                base_raw = os.path.join("storage", doc_type_id, "02_raw_data")
                pending_folder_name = f"{tax_id}_{old_short_name}" if tax_id != "NO_TAXID" else old_short_name
                pending_dir = os.path.join(base_raw, "PENDING", pending_folder_name)

                approved_folder_name = f"{tax_id}_{final_short_name}" if tax_id != "NO_TAXID" else final_short_name
                approved_dir = os.path.join(base_raw, approved_folder_name)

                if os.path.exists(pending_dir):
                    os.makedirs(approved_dir, exist_ok=True)
                    for item in os.listdir(pending_dir):
                        src_file = os.path.join(pending_dir, item)
                        dst_file = os.path.join(approved_dir, item)
                        if os.path.isfile(src_file):
                            os.replace(src_file, dst_file)
                    try:
                        os.rmdir(pending_dir)
                    except Exception:
                        pass
                else:
                    os.makedirs(approved_dir, exist_ok=True)
                    with open(os.path.join(approved_dir, ".gitkeep"), "w", encoding="utf-8") as gf:
                        gf.write("# Merchant folder ready\n")
            except Exception as fe:
                logger.warning(f"File relocation warning on approving merchant: {fe}")

            logger.info(f"Merchant '{merchant_id}' approved as '{final_short_name}' (prefix: '{final_prefix}') by '{approved_by}'.")
            return True, f"Merchant '{merchant.merchant_name}' approved successfully."
    except Exception as e:
        logger.error(f"Failed to approve merchant '{merchant_id}': {e}")
        return False, str(e)


def ignore_merchant(merchant_id: str, approved_by: str = "admin", doc_type_id: str = "expense_receipt") -> tuple[bool, str]:
    """
    Marks a merchant as IGNORED status.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    try:
        with get_db_session() as session:
            merchant = session.query(Merchant).filter_by(merchant_id=merchant_id).first()
            if not merchant:
                return False, f"Merchant ID '{merchant_id}' not found."

            merchant.status_code = MerchantStatus.IGNORED.value
            merchant.approved_by = approved_by
            merchant.approved_at = now_str
            merchant.updated_at = now_str

            tax_id = merchant.tax_id or "NO_TAXID"
            short_name = merchant.short_name or "merchant"

            try:
                base_raw = os.path.join("storage", doc_type_id, "02_raw_data")
                folder_name = f"{tax_id}_{short_name}" if tax_id != "NO_TAXID" else short_name
                pending_dir = os.path.join(base_raw, "PENDING", folder_name)
                ignored_dir = os.path.join(base_raw, "IGNORED", folder_name)

                if os.path.exists(pending_dir):
                    os.makedirs(ignored_dir, exist_ok=True)
                    for item in os.listdir(pending_dir):
                        src_file = os.path.join(pending_dir, item)
                        dst_file = os.path.join(ignored_dir, item)
                        if os.path.isfile(src_file):
                            os.replace(src_file, dst_file)
                    try:
                        os.rmdir(pending_dir)
                    except Exception:
                        pass
                else:
                    os.makedirs(ignored_dir, exist_ok=True)
                    with open(os.path.join(ignored_dir, ".gitkeep"), "w", encoding="utf-8") as gf:
                        gf.write("# Merchant ignored folder\n")
            except Exception as fe:
                logger.warning(f"File relocation warning on ignoring merchant: {fe}")

            logger.info(f"Merchant '{merchant_id}' marked as IGNORED by '{approved_by}'.")
            return True, f"Merchant '{merchant.merchant_name}' set to IGNORED."
    except Exception as e:
        logger.error(f"Failed to ignore merchant '{merchant_id}': {e}")
        return False, str(e)


def upsert_merchant(merchant_data: dict) -> bool:
    """
    Inserts or updates a merchant record in merchants table using SQLAlchemy ORM.
    """
    try:
        with get_db_session() as session:
            m_id = merchant_data.get("merchant_id")
            if not m_id:
                m_id = f"merch_{uuid.uuid4().hex[:8]}"

            merchant = session.query(Merchant).filter_by(merchant_id=m_id).first()
            now_str = datetime.now(timezone.utc).isoformat()

            if merchant:
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
                new_m = Merchant(
                    merchant_id=m_id,
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


def match_merchant(tax_id: str, name: str) -> str | None:
    """
    Matches a merchant from merchants by tax_id first, then by merchant_name using SQLAlchemy ORM.
    Returns merchant_id if matched, otherwise None.
    """
    try:
        with get_db_session() as session:
            # 1. Match by Tax ID (exact match)
            if tax_id and tax_id.strip():
                merchant = session.query(Merchant).filter_by(tax_id=tax_id.strip()).first()
                if merchant:
                    return merchant.merchant_id

            # 2. Match by Merchant Name (case-insensitive match)
            if name and name.strip():
                merchant = session.query(Merchant).filter(
                    func.lower(Merchant.merchant_name) == name.strip().lower()
                ).first()
                if merchant:
                    return merchant.merchant_id
    except Exception as e:
        logger.error(f"Error matching merchant: {e}")
    return None


def delete_merchant(merchant_id: str) -> bool:
    """
    Deletes a merchant record from merchants using SQLAlchemy ORM.
    """
    try:
        with get_db_session() as session:
            merchant = session.query(Merchant).filter_by(merchant_id=merchant_id).first()
            if merchant:
                session.delete(merchant)
                return True
            return False
    except Exception as e:
        logger.error(f"Failed to delete merchant '{merchant_id}': {e}")
        return False


def insert_relational_receipt(document_id: str, payload: dict, original_filename: str) -> bool:
    """
    Parses extracted JSON payload and inserts header and items into relational tables using SQLAlchemy ORM.
    Also auto-registers new merchants in merchants table.
    """
    try:
        with get_db_session() as session:
            now_str = datetime.now(timezone.utc).isoformat()

            # 1. Extract merchant & receipt information with fallbacks
            merchant_obj = payload.get("merchant", {})
            receipt_info = payload.get("receipt_info", {})
            totals_obj = payload.get("totals", {}) or payload.get("financial_summary", {})

            merchant_name = merchant_obj.get("name") or payload.get("merchant_name") or "Unknown Merchant"
            tax_id = merchant_obj.get("tax_id") or payload.get("tax_id")
            if tax_id:
                tax_id = tax_id.strip()

            # 2. Match merchant in merchants
            merchant_id = match_merchant(tax_id, merchant_name)
            if not merchant_id:
                merchant_id = f"mer_{uuid.uuid4().hex[:12]}"
                short_name = sanitize_short_name(merchant_name)
                new_m = Merchant(
                    merchant_id=merchant_id,
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
            existing_receipts = session.query(ExpenseReceipt).filter_by(document_id=document_id).all()
            for r in existing_receipts:
                session.delete(r)
            session.flush()

            receipt_id = f"rcpt_{uuid.uuid4().hex[:12]}"

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
                    item_id=f"itm_{uuid.uuid4().hex[:12]}",
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
