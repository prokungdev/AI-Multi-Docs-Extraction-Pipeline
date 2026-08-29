"""Journal Voucher Generator Use Case (Application Layer).

Transforms approved financial documents (DocumentControl + ExpenseReceipt + Merchant)
into Canonical Journal Vouchers (JournalVoucher + JournalVoucherItem) and generates
the destination target ERP/RPA payloads (e.g. Express OE Screen JSON) via Plugin Adapters.
"""

from typing import Dict, Any, Optional, List
from sqlalchemy import select

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import (
    ConsolidateModeCode,
    VatType,
    VoucherStatusCode,
)
from src.infrastructure.database.engine import get_db_session
from src.infrastructure.database.models import (
    DocumentControl,
    ExpenseReceipt,
    Merchant,
    Company,
)
from src.infrastructure.database import (
    generate_next_voucher_no,
    create_journal_voucher,
    get_journal_voucher_by_document_id,
    get_expense_account_mapping,
)
from src.application.exporters import TargetAdapterRegistry


def generate_voucher_for_document(document_id: str) -> Dict[str, Any]:
    """
    Generates a Canonical Journal Voucher for an approved DocumentControl and its ExpenseReceipt.
    
    1. Loads DocumentControl, ExpenseReceipt, Merchant, and Company
    2. Resolves company.active_target_system_id (default: EXPRESS)
    3. Handles running number generation based on company.auto_gen_voucher_no
    4. Applies line consolidation logic based on merchant.consolidate_mode
    5. Resolves GL account codes from ExpenseAccountMapping
    6. Transforms to target system payload (e.g. Express OE Screen JSON)
    7. Inserts JournalVoucher & items into DB with status READY
    """
    if not document_id or not str(document_id).strip():
        raise ValueError("document_id is required for voucher generation (Fail-Fast).")

    clean_doc_id = str(document_id).strip()

    # Check if voucher already exists for this document
    existing_vch = get_journal_voucher_by_document_id(clean_doc_id)
    if existing_vch:
        logger.info(f"JournalVoucher already exists for document '{clean_doc_id}': {existing_vch['voucher_no']}")
        return existing_vch

    with get_db_session() as session:
        # 1. Load DocumentControl
        doc = session.scalars(select(DocumentControl).filter_by(document_id=clean_doc_id)).first()
        if not doc:
            raise KeyError(f"DocumentControl '{clean_doc_id}' not found in database.")

        # 2. Load ExpenseReceipt
        receipt = session.scalars(select(ExpenseReceipt).filter_by(document_id=clean_doc_id)).first()
        if not receipt:
            raise KeyError(f"ExpenseReceipt for document '{clean_doc_id}' not found in database.")

        # 3. Load Company
        company = session.scalars(select(Company).filter_by(company_id=doc.company_id)).first()
        if not company:
            raise KeyError(f"Company '{doc.company_id}' not found in database.")

        # 4. Load Merchant
        merchant = None
        if receipt.merchant_id:
            merchant = session.scalars(select(Merchant).filter_by(merchant_id=receipt.merchant_id)).first()

        doc_dict = doc.to_dict()
        receipt_dict = receipt.to_dict()
        items_dict = [it.to_dict() for it in receipt.items]
        receipt_dict["items"] = items_dict
        company_dict = company.to_dict()
        merchant_dict = merchant.to_dict() if merchant else {}

    # Target system resolution
    target_sys_id = company_dict.get("active_target_system_id") or "EXPRESS"
    auto_gen_no = bool(company_dict.get("auto_gen_voucher_no", 1))

    # Date normalization
    voucher_date = receipt_dict.get("transaction_date") or receipt_dict.get("created_at", "")[:10]
    if len(voucher_date) > 10:
        voucher_date = voucher_date[:10]

    # Voucher Number resolution
    if auto_gen_no:
        voucher_no = generate_next_voucher_no(
            company_id=company_dict["company_id"],
            voucher_type="OE",
            voucher_date_str=voucher_date,
        )
    else:
        voucher_no = None

    # Merchant config attributes
    vendor_code = (
        merchant_dict.get("vendor_code")
        or (merchant_dict.get("tax_id") if merchant_dict else None)
        or "MISC"
    )
    vendor_name = merchant_dict.get("merchant_name") or receipt_dict.get("merchant_name") or "Unknown Vendor"
    vendor_tax_id = merchant_dict.get("tax_id") or receipt_dict.get("tax_id")
    expense_type_name = merchant_dict.get("default_expense_type") or "ค่าบริการ"
    vat_type = merchant_dict.get("default_vat_type") or "EXCLUSIVE"
    consolidate_mode = merchant_dict.get("consolidate_mode") or ConsolidateModeCode.BY_MERCHANT.value

    # GL Account mapping lookup
    account_mapping = get_expense_account_mapping(
        company_id=company_dict["company_id"],
        target_system_id=target_sys_id,
        expense_type_name=expense_type_name,
    )
    default_acc_code = account_mapping.get("account_code") if account_mapping else "5999-99"
    default_acc_name = account_mapping.get("account_name") if account_mapping else "ค่าใช้จ่ายเบ็ดเตล็ด"
    dept_code = account_mapping.get("department_code", "") if account_mapping else ""

    # Financial amounts
    subtotal = round(float(receipt_dict.get("subtotal") or 0.0), 2)
    vat_amount = round(float(receipt_dict.get("vat_amount") or 0.0), 2)
    net_amount = round(float(receipt_dict.get("net_amount") or 0.0), 2)

    has_wht = bool(merchant_dict.get("has_wht", 0) or receipt_dict.get("has_wht", 0))
    wht_rate = float(merchant_dict.get("default_wht_rate") or receipt_dict.get("wht_rate") or 0.0)
    wht_amount = round(float(receipt_dict.get("wht_amount") or 0.0), 2)
    if has_wht and wht_amount == 0.0 and wht_rate > 0.0 and subtotal > 0.0:
        wht_amount = round(subtotal * (wht_rate / 100.0), 2)

    # 5. Build Journal Voucher Line Items based on consolidate_mode
    voucher_items: List[Dict[str, Any]] = []

    if consolidate_mode == ConsolidateModeCode.NO_CONSOLIDATION.value and items_dict:
        # Separate line for each OCR line item
        for idx, it in enumerate(items_dict, start=1):
            it_amt = round(float(it.get("total_price") or it.get("unit_price") or 0.0), 2)
            it_desc = it.get("item_name") or f"{vendor_name} line {idx}"
            voucher_items.append({
                "line_number": idx,
                "entry_type": "DEBIT",
                "account_code": default_acc_code,
                "account_name": default_acc_name,
                "department_code": dept_code,
                "amount": it_amt,
                "description": it_desc,
            })
    else:
        # Default: Single Summary Line (BY_MERCHANT)
        voucher_items.append({
            "line_number": 1,
            "entry_type": "DEBIT",
            "account_code": default_acc_code,
            "account_name": default_acc_name,
            "department_code": dept_code,
            "amount": subtotal if subtotal > 0.0 else net_amount,
            "description": f"{vendor_name} ({voucher_date})",
        })

    # Canonical Voucher Record
    voucher_data = {
        "document_id": clean_doc_id,
        "company_id": company_dict["company_id"],
        "batch_id": doc_dict.get("batch_id"),
        "target_system_id": target_sys_id,
        "voucher_type": "OE",
        "voucher_no": voucher_no,
        "voucher_date": voucher_date,
        "vendor_code": vendor_code,
        "vendor_name": vendor_name,
        "vendor_tax_id": vendor_tax_id,
        "ref_doc_no": receipt_dict.get("doc_number"),
        "ref_doc_date": voucher_date,
        "subtotal_amount": subtotal,
        "vat_type": vat_type,
        "vat_rate": 7.0 if vat_type != VatType.NO_VAT.value else 0.0,
        "vat_amount": vat_amount,
        "wht_amount": wht_amount,
        "net_amount": net_amount,
        "status_code": VoucherStatusCode.READY.value,
        "items": voucher_items,
    }

    # 6. Transform using Destination ERP Target Adapter
    adapter = TargetAdapterRegistry.get_adapter(target_sys_id)
    target_payload = adapter.transform_voucher(
        voucher=voucher_data,
        merchant_config=merchant_dict,
        account_mapping=account_mapping,
    )
    voucher_data["target_payload"] = target_payload

    # 7. Persist Journal Voucher
    created_voucher = create_journal_voucher(voucher_data=voucher_data, items_data=voucher_items)
    logger.info(
        f"Generated JournalVoucher {created_voucher.get('voucher_no')} for Document '{clean_doc_id}' "
        f"Target: {target_sys_id} -> Status: READY"
    )
    return created_voucher


def generate_vouchers_for_batch(batch_id: str) -> List[Dict[str, Any]]:
    """
    Generates Journal Vouchers for all APPROVED documents within a batch.
    """
    if not batch_id or not str(batch_id).strip():
        raise ValueError("batch_id is required for batch voucher generation.")

    clean_batch_id = str(batch_id).strip()
    generated = []

    with get_db_session() as session:
        stmt = (
            select(DocumentControl.document_id)
            .where(
                DocumentControl.batch_id == clean_batch_id,
                DocumentControl.status_code == "APPROVED",
            )
        )
        doc_ids = session.scalars(stmt).all()

    for doc_id in doc_ids:
        try:
            vch = generate_voucher_for_document(doc_id)
            generated.append(vch)
        except Exception as e:
            logger.error(f"Failed to generate voucher for document '{doc_id}': {e}")

    logger.info(f"Generated {len(generated)}/{len(doc_ids)} Journal Voucher(s) for Batch '{clean_batch_id}'.")
    return generated
