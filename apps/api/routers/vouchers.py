"""Voucher Management and UiPath RPA Gateway API Router.

Provides high-concurrency endpoints for UiPath Robots and external clients:
- POST /api/v1/vouchers/get-next (Acquire next voucher + lease lock)
- GET /api/v1/vouchers/get-next (Preview next voucher without lock)
- POST /api/v1/vouchers/{voucher_id}/complete (Report success and store ERP reference)
- POST /api/v1/vouchers/{voucher_id}/fail (Report RPA error and store trace)
- POST /api/v1/vouchers/{voucher_id}/unlock (Release lock back to READY)
- GET /api/v1/vouchers/{voucher_id} (Inspect voucher detail)
"""

import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Query

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import VoucherStatusCode
from src.infrastructure.database import (
    lease_next_ready_voucher,
    release_or_unlock_voucher,
    update_voucher_status,
    get_journal_voucher_by_id,
    list_vouchers,
)
from src.application.dtos.voucher_dto import (
    VoucherGetNextRequest,
    VoucherCompleteRequest,
    VoucherFailRequest,
    VoucherPayloadDTO,
    VoucherLineItemDTO,
    VoucherResponseWrapper,
)

router = APIRouter(prefix="/vouchers", tags=["Vouchers RPA Gateway"])


def _build_payload_dto(voucher_dict: Dict[str, Any]) -> VoucherPayloadDTO:
    """Helper to construct a standardized VoucherPayloadDTO from voucher dict."""
    target_payload = voucher_dict.get("target_payload_parsed")
    if not target_payload and voucher_dict.get("target_payload"):
        try:
            target_payload = json.loads(voucher_dict["target_payload"])
        except Exception:
            target_payload = None

    if isinstance(target_payload, dict):
        raw_lines = target_payload.get("lines") or []
        lines_dto = [
            VoucherLineItemDTO(
                account_code=l.get("account_code", "5999-99"),
                amount=float(l.get("amount", 0.0)),
                description=l.get("description"),
            )
            for l in raw_lines
        ]

        return VoucherPayloadDTO(
            voucher_id=voucher_dict.get("voucher_id", ""),
            voucher_no=target_payload.get("voucher_no") or voucher_dict.get("voucher_no"),
            voucher_date=target_payload.get("voucher_date", ""),
            vendor_code=target_payload.get("vendor_code", "MISC"),
            ref_bill_no=target_payload.get("ref_bill_no", ""),
            ref_bill_date=target_payload.get("ref_bill_date", ""),
            vat_type_id=int(target_payload.get("vat_type_id", 2)),
            subtotal=float(target_payload.get("subtotal", 0.0)),
            vat_amount=float(target_payload.get("vat_amount", 0.0)),
            wht_no=target_payload.get("wht_no"),
            wht_rate=float(target_payload.get("wht_rate", 0.0)),
            wht_amount=float(target_payload.get("wht_amount", 0.0)),
            lines=lines_dto,
        )

    # Fallback from raw voucher dict if target_payload missing
    items = voucher_dict.get("items") or []
    lines_dto = [
        VoucherLineItemDTO(
            account_code=it.get("account_code", "5999-99"),
            amount=float(it.get("amount", 0.0)),
            description=it.get("description"),
        )
        for it in items
    ]

    return VoucherPayloadDTO(
        voucher_id=voucher_dict.get("voucher_id", ""),
        voucher_no=voucher_dict.get("voucher_no"),
        voucher_date=voucher_dict.get("voucher_date", ""),
        vendor_code=voucher_dict.get("vendor_code", "MISC"),
        ref_bill_no=voucher_dict.get("ref_doc_no", "") or "",
        ref_bill_date=voucher_dict.get("ref_doc_date", "") or voucher_dict.get("voucher_date", ""),
        vat_type_id=2,
        subtotal=float(voucher_dict.get("subtotal_amount", 0.0)),
        vat_amount=float(voucher_dict.get("vat_amount", 0.0)),
        wht_no=None,
        wht_rate=0.0,
        wht_amount=float(voucher_dict.get("wht_amount", 0.0)),
        lines=lines_dto,
    )


@router.post("/get-next", response_model=VoucherResponseWrapper)
def get_next_voucher_post(request: Optional[VoucherGetNextRequest] = None):
    """
    Leases the next pending voucher for UiPath RPA Bot processing.
    
    - Transitions status from READY -> POSING (or re-claims an expired lock).
    - If preview=True, retrieves the voucher without acquiring lease lock.
    """
    req = request or VoucherGetNextRequest()

    if req.preview:
        ready_list = list_vouchers(
            target_system_id=req.target_system_id,
            status_code=VoucherStatusCode.READY.value,
            limit=1
        )
        if not ready_list:
            return VoucherResponseWrapper(
                status="success",
                message="No pending vouchers available (Preview).",
                data=None
            )
        vch = get_journal_voucher_by_id(ready_list[0]["voucher_id"])
        payload_dto = _build_payload_dto(vch)
        return VoucherResponseWrapper(
            status="success",
            message="Voucher preview retrieved successfully.",
            data=payload_dto
        )

    # Actual Lease Lock
    leased = lease_next_ready_voucher(
        target_system_id=req.target_system_id,
        bot_id=req.bot_id,
    )

    if not leased:
        return VoucherResponseWrapper(
            status="success",
            message="No pending vouchers available.",
            data=None
        )

    payload_dto = _build_payload_dto(leased)
    return VoucherResponseWrapper(
        status="success",
        message="Voucher leased successfully.",
        data=payload_dto
    )


@router.get("/get-next", response_model=VoucherResponseWrapper)
def get_next_voucher_get(
    target_system_id: str = Query(default="EXPRESS", description="Target System ID"),
    preview: bool = Query(default=True, description="Default True for GET requests to prevent accidental locking"),
    bot_id: str = Query(default="uipath_browser", description="Robot / Client ID")
):
    """
    Preview or fetch the next pending voucher via HTTP GET.
    Defaults to preview=True (Read-Only) to comply with HTTP GET idempotency standards.
    """
    req = VoucherGetNextRequest(
        target_system_id=target_system_id,
        preview=preview,
        bot_id=bot_id
    )
    return get_next_voucher_post(req)


@router.post("/{voucher_id}/complete")
def complete_voucher(voucher_id: str, request: Optional[VoucherCompleteRequest] = None):
    """
    Reports successful posting of a voucher by UiPath RPA Bot.
    Transitions status to POSTED and records ERP reference number.
    """
    req = request or VoucherCompleteRequest()
    try:
        updated = update_voucher_status(
            voucher_id=voucher_id,
            status_code=VoucherStatusCode.POSTED.value,
            erp_reference_no=req.erp_reference_no,
        )
        return {
            "status": "success",
            "message": f"Voucher {updated.get('voucher_no')} marked as POSTED successfully.",
            "voucher_id": voucher_id,
            "erp_reference_no": req.erp_reference_no,
            "posted_at": updated.get("posted_at"),
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to complete voucher '{voucher_id}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{voucher_id}/fail")
def fail_voucher(voucher_id: str, request: VoucherFailRequest):
    """
    Reports failed posting of a voucher by UiPath RPA Bot.
    Transitions status to ERROR and records the failure reason.
    """
    try:
        updated = update_voucher_status(
            voucher_id=voucher_id,
            status_code=VoucherStatusCode.ERROR.value,
            error_message=request.error_message,
        )
        return {
            "status": "success",
            "message": f"Voucher {updated.get('voucher_no')} marked as ERROR.",
            "voucher_id": voucher_id,
            "error_message": request.error_message,
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to record failure for voucher '{voucher_id}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{voucher_id}/unlock")
def unlock_voucher(voucher_id: str):
    """
    Unlocks a leased/posing voucher and returns its status back to READY.
    """
    try:
        success = release_or_unlock_voucher(voucher_id=voucher_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Voucher '{voucher_id}' not found or could not be unlocked."
            )
        return {
            "status": "success",
            "message": f"Voucher '{voucher_id}' unlocked back to READY.",
            "voucher_id": voucher_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unlock voucher '{voucher_id}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{voucher_id}")
def get_voucher_detail(voucher_id: str):
    """
    Retrieves full details of a Journal Voucher by its voucher_id.
    """
    vch = get_journal_voucher_by_id(voucher_id)
    if not vch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voucher '{voucher_id}' not found."
        )
    return {
        "status": "success",
        "data": vch,
    }
