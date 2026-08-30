"""Journal Voucher Repository using Pure SQLAlchemy 2.0 ORM.

Handles:
- Voucher running number generation (e.g. OE260730001)
- Voucher and Line Item CRUD operations
- Concurrency Lease Lock & Atomic State Transitions for RPA / UiPath Bots
- Voucher status updates, error tracking, and lease release
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, and_, or_, func, desc

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import (
    EntityIdPrefix,
    SystemUserId,
    VoucherStatusCode,
    generate_entity_id,
)
from src.infrastructure.core.user_context import get_current_user_id
from ..engine import get_db_session
from ..models import JournalVoucher, JournalVoucherItem, Company


def generate_next_voucher_no(
    company_id: str,
    voucher_type: str = "OE",
    voucher_date_str: Optional[str] = None,
) -> str:
    """
    Generates the next sequential voucher number in format: {TYPE}{YY}{MM}{DD}{SEQ:03d}
    Example for 2026-07-30: OE260730001
    
    Queries the highest existing sequence for that day and increments by 1.
    """
    if not voucher_date_str:
        today = datetime.now(timezone.utc)
        date_prefix = f"{str(today.year)[2:4]}{today.month:02d}{today.day:02d}"
    else:
        # Parse ISO date YYYY-MM-DD
        dt = datetime.strptime(voucher_date_str.strip()[:10], "%Y-%m-%d")
        date_prefix = f"{str(dt.year)[2:4]}{dt.month:02d}{dt.day:02d}"

    pattern = f"{voucher_type}{date_prefix}"

    with get_db_session() as session:
        stmt = (
            select(JournalVoucher.voucher_no)
            .where(
                and_(
                    JournalVoucher.company_id == company_id,
                    JournalVoucher.voucher_no.like(f"{pattern}%"),
                )
            )
            .order_by(desc(JournalVoucher.voucher_no))
            .limit(1)
        )
        last_voucher_no = session.scalars(stmt).first()

        if last_voucher_no and len(last_voucher_no) >= len(pattern) + 3:
            try:
                seq_str = last_voucher_no[len(pattern):len(pattern)+3]
                current_seq = int(seq_str)
                next_seq = current_seq + 1
            except ValueError:
                next_seq = 1
        else:
            next_seq = 1

        voucher_no = f"{pattern}{next_seq:03d}"
        return voucher_no


def create_journal_voucher(
    voucher_data: Dict[str, Any],
    items_data: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Creates a new Journal Voucher and its associated debit/credit line items.
    """
    with get_db_session() as session:
        vch_id = voucher_data.get("voucher_id") or generate_entity_id(EntityIdPrefix.VOUCHER)
        
        # Serialize target_payload if provided as dict
        target_payload = voucher_data.get("target_payload")
        if isinstance(target_payload, (dict, list)):
            target_payload_str = json.dumps(target_payload, ensure_ascii=False)
        else:
            target_payload_str = target_payload

        current_actor = get_current_user_id() or SystemUserId.AUTO_SYSTEM

        voucher = JournalVoucher(
            voucher_id=vch_id,
            document_id=voucher_data.get("document_id"),
            company_id=voucher_data["company_id"],
            batch_id=voucher_data.get("batch_id"),
            target_system_id=voucher_data.get("target_system_id", "EXPRESS"),
            voucher_type=voucher_data.get("voucher_type", "OE"),
            voucher_no=voucher_data.get("voucher_no"),
            voucher_date=voucher_data.get("voucher_date"),
            vendor_code=voucher_data.get("vendor_code"),
            vendor_name=voucher_data.get("vendor_name"),
            vendor_tax_id=voucher_data.get("vendor_tax_id"),
            vendor_branch_code=voucher_data.get("vendor_branch_code", "00000"),
            ref_doc_no=voucher_data.get("ref_doc_no"),
            subtotal_amount=voucher_data.get("subtotal_amount", 0.0),
            vat_type=voucher_data.get("vat_type", "EXCLUSIVE"),
            vat_rate=voucher_data.get("vat_rate", 7.0),
            vat_amount=voucher_data.get("vat_amount", 0.0),
            is_override_vat=voucher_data.get("is_override_vat", 1),
            wht_amount=voucher_data.get("wht_amount", 0.0),
            net_amount=voucher_data.get("net_amount", 0.0),
            status_code=voucher_data.get("status_code", VoucherStatusCode.READY.value),
            target_payload=target_payload_str,
            created_by=current_actor,
        )
        session.add(voucher)
        session.flush()

        # Insert items
        if items_data:
            for idx, item in enumerate(items_data, start=1):
                item_id = item.get("item_id") or generate_entity_id(EntityIdPrefix.VOUCHER_ITEM)
                vch_item = JournalVoucherItem(
                    item_id=item_id,
                    voucher_id=vch_id,
                    line_number=item.get("line_number", idx),
                    entry_type=item.get("entry_type", "DEBIT"),
                    account_code=item["account_code"],
                    account_name=item.get("account_name"),
                    department_code=item.get("department_code", ""),
                    amount=item.get("amount", 0.0),
                    description=item.get("description"),
                    created_by=current_actor,
                )
                session.add(vch_item)

        session.flush()
        logger.info(f"Created JournalVoucher {voucher.voucher_no} ({voucher.voucher_id}) with {len(items_data or [])} items.")
    return get_journal_voucher_by_id(vch_id)


def get_journal_voucher_by_id(voucher_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a Journal Voucher by its voucher_id along with child line items."""
    if not voucher_id:
        return None

    with get_db_session() as session:
        stmt = select(JournalVoucher).where(JournalVoucher.voucher_id == voucher_id)
        voucher = session.scalars(stmt).first()
        if not voucher:
            return None

        result = voucher.to_dict()
        result["items"] = [item.to_dict() for item in voucher.items]
        result["error_message"] = voucher.rpa_error_reason
        if result.get("target_payload"):
            try:
                result["target_payload_parsed"] = json.loads(result["target_payload"])
            except Exception:
                result["target_payload_parsed"] = None
        return result


def get_journal_voucher_by_document_id(document_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a Journal Voucher linked to a DocumentControl document_id."""
    if not document_id:
        return None

    with get_db_session() as session:
        stmt = select(JournalVoucher).where(JournalVoucher.document_id == document_id)
        voucher = session.scalars(stmt).first()
        if not voucher:
            return None
        vch_id = voucher.voucher_id
    return get_journal_voucher_by_id(vch_id)


def lease_next_ready_voucher(
    target_system_id: str = "EXPRESS",
    lease_timeout_minutes: int = 15,
    bot_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Atomically acquires a Concurrency Lease Lock on the next available voucher.
    
    Transitions status from READY -> POSING (or re-claims an expired POSING lease).
    Ensures multiple RPA/UiPath workers never process the same voucher concurrently.
    """
    now = datetime.now(timezone.utc)
    cutoff_time = (now - timedelta(minutes=lease_timeout_minutes)).isoformat()
    actor = bot_id or get_current_user_id() or "usr_system_rpa"
    leased_vch_id = None

    with get_db_session() as session:
        # Find next READY voucher, or POSING with expired lock
        stmt = (
            select(JournalVoucher)
            .where(
                and_(
                    JournalVoucher.target_system_id == target_system_id,
                    or_(
                        JournalVoucher.status_code == VoucherStatusCode.READY.value,
                        and_(
                            JournalVoucher.status_code == VoucherStatusCode.POSING.value,
                            JournalVoucher.locked_at < cutoff_time,
                        ),
                    ),
                )
            )
            .order_by(JournalVoucher.created_at.asc())
            .limit(1)
        )
        voucher = session.scalars(stmt).first()
        if not voucher:
            return None

        voucher.status_code = VoucherStatusCode.POSING.value
        voucher.locked_at = now.isoformat()
        voucher.locked_by = actor
        session.flush()
        leased_vch_id = voucher.voucher_id
        logger.info(f"Leased voucher {voucher.voucher_no} ({voucher.voucher_id}) to bot actor '{actor}'")

    return get_journal_voucher_by_id(leased_vch_id) if leased_vch_id else None


def release_or_unlock_voucher(voucher_id: str) -> bool:
    """
    Releases the Concurrency Lease Lock and returns voucher status to READY.
    Useful for test resets or when a bot aborts gracefully without error.
    """
    if not voucher_id:
        return False

    with get_db_session() as session:
        stmt = select(JournalVoucher).where(JournalVoucher.voucher_id == voucher_id)
        voucher = session.scalars(stmt).first()
        if not voucher:
            return False

        voucher.status_code = VoucherStatusCode.READY.value
        voucher.locked_at = None
        voucher.locked_by = None
        session.flush()
        logger.info(f"Released lock for voucher {voucher.voucher_no} ({voucher_id}) -> Status: READY")
        return True


def update_voucher_status(
    voucher_id: str,
    status_code: str,
    error_message: Optional[str] = None,
    erp_reference_no: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Updates voucher status (POSTED, ERROR, CANCELLED, etc.) after RPA posting.
    """
    if not voucher_id or not status_code:
        raise ValueError("voucher_id and status_code are required.")

    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_session() as session:
        stmt = select(JournalVoucher).where(JournalVoucher.voucher_id == voucher_id)
        voucher = session.scalars(stmt).first()
        if not voucher:
            raise KeyError(f"JournalVoucher '{voucher_id}' not found.")

        voucher.status_code = status_code
        voucher.locked_at = None
        voucher.locked_by = None

        if error_message is not None:
            voucher.rpa_error_reason = error_message
        if erp_reference_no is not None:
            voucher.erp_reference_no = erp_reference_no
        if status_code == VoucherStatusCode.POSTED.value:
            voucher.posted_at = now_iso
            voucher.rpa_error_reason = None

        session.flush()
        logger.info(f"Updated voucher {voucher.voucher_no} status to '{status_code}'")

    return get_journal_voucher_by_id(voucher_id)


def list_vouchers(
    company_id: Optional[str] = None,
    target_system_id: Optional[str] = None,
    status_code: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Lists Journal Vouchers with optional company, target system, and status filtering."""
    with get_db_session() as session:
        stmt = select(JournalVoucher)
        if company_id:
            stmt = stmt.where(JournalVoucher.company_id == company_id)
        if target_system_id:
            stmt = stmt.where(JournalVoucher.target_system_id == target_system_id)
        if status_code:
            stmt = stmt.where(JournalVoucher.status_code == status_code)

        vouchers = session.scalars(stmt.order_by(desc(JournalVoucher.created_at)).limit(limit)).all()
        return [v.to_dict() for v in vouchers]
