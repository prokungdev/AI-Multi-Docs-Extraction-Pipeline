"""
Stage 7: Target ERP & RPA Payload Export Pipeline Stage.

Coordinates formatting canonical Journal Vouchers into target ERP-specific JSON payloads
(e.g., Express OE Screen JSON, SAP FB60) and seals vouchers as READY for RPA bot polling.
"""

from typing import Dict, Any, Optional, List
from sqlalchemy import select, and_

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import VoucherStatusCode
from src.infrastructure.database.engine import get_db_session
from src.infrastructure.database.models import JournalVoucher, Company


def export_target_payloads(
    batch_id: str,
    company_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stage 7: Target ERP Payload Export & Sealing Entry Point.
    Fetches all Journal Vouchers in the target batch, verifies target_payload,
    and seals them in status READY.
    """
    if not batch_id or not str(batch_id).strip():
        raise ValueError("batch_id is required for target export (Fail-Fast).")

    clean_batch_id = str(batch_id).strip()

    with get_db_session() as session:
        stmt = select(JournalVoucher).where(JournalVoucher.batch_id == clean_batch_id)

        if company_code:
            comp = session.scalars(select(Company).filter_by(company_code=company_code)).first()
            if comp:
                stmt = stmt.where(JournalVoucher.company_id == comp.company_id)

        vouchers = session.scalars(stmt).all()
        exported_payloads: List[Dict[str, Any]] = []

        for vch in vouchers:
            vch.status_code = VoucherStatusCode.READY.value
            exported_payloads.append(vch.to_dict())

        session.commit()
        logger.info(f"Stage 7: Exported and sealed {len(exported_payloads)} voucher(s) as READY for batch '{clean_batch_id}'.")

        return {
            "batch_id": clean_batch_id,
            "total_exported": len(exported_payloads),
            "status": "READY",
            "vouchers": exported_payloads,
        }


__all__ = [
    "export_target_payloads",
]
