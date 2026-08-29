"""Financial Domain Receipt Subtype repository using Pure SQLAlchemy 2.0 ORM."""

from datetime import datetime, timezone
from sqlalchemy import select

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import (
    DefaultIdentifier,
    EntityIdPrefix,
    SystemUserId,
    generate_entity_id,
)
from ..engine import get_db_session
from ..models import Company, DocumentControl, Merchant, MerchantStatus, ExpenseReceipt, ExpenseReceiptItem
from .merchant_repo import match_merchant, sanitize_short_name


def insert_relational_receipt(
    document_id: str,
    payload: dict,
    original_filename: str,
    created_by: str,
    company_id: str = None,
    page_number: int = 1
) -> bool:
    """
    Parses extracted JSON payload and inserts header and items into relational tables using Pure SQLAlchemy 2.0 ORM.
    Supports both unwrapped single document dict and wrapped multi-page AI payload.
    Also auto-registers new merchants in merchants table. Requires created_by.
    """
    try:
        from src.application.pipeline.pipeline_helpers import extract_page_document_payload
        doc_payload = extract_page_document_payload(payload, page_number=page_number)

        with get_db_session() as session:
            now_str = datetime.now(timezone.utc).isoformat()

            # Target company resolution
            target_cid = company_id
            if not target_cid:
                doc = session.scalars(select(DocumentControl).filter_by(document_id=document_id)).first()
                if doc and doc.company_id:
                    target_cid = doc.company_id
                else:
                    def_comp = session.scalars(select(Company).filter_by(company_code=DefaultIdentifier.COMPANY_CODE)).first()
                    if def_comp:
                        target_cid = def_comp.company_id

            # 1. Extract merchant & receipt information with fallbacks
            merchant_obj = doc_payload.get("merchant", {})
            receipt_info = doc_payload.get("receipt_info", {})
            totals_obj = doc_payload.get("totals", {}) or doc_payload.get("financial_summary", {})

            merchant_name = merchant_obj.get("name") or doc_payload.get("merchant_name") or "Unknown Merchant"
            tax_id = merchant_obj.get("tax_id") or doc_payload.get("tax_id")
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
                    created_at=now_str,
                    created_by=created_by
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
            subtotal = float(totals_obj.get("subtotal", 0.0))
            discount = float(totals_obj.get("discount", 0.0))
            vat_amount = float(totals_obj.get("vat_amount", 0.0))
            net_amount = float(totals_obj.get("net_amount", 0.0))
            wht_amount = float(totals_obj.get("wht_amount", 0.0) or totals_obj.get("withholding_tax_amount", 0.0))
            wht_rate = float(totals_obj.get("wht_rate", 0.0) or totals_obj.get("withholding_tax_rate", 0.0))
            has_wht = 1 if wht_amount > 0 or wht_rate > 0 else 0

            doc_number = receipt_info.get("receipt_number") or doc_payload.get("doc_number")
            transaction_date = receipt_info.get("transaction_date") or doc_payload.get("transaction_date")
            expense_category = receipt_info.get("expense_category") or doc_payload.get("expense_category")
            payment_method = receipt_info.get("payment_method") or doc_payload.get("payment_method")

            receipt = ExpenseReceipt(
                receipt_id=receipt_id,
                company_id=target_cid,
                document_id=document_id,
                merchant_id=merchant_id,
                doc_number=doc_number,
                transaction_date=transaction_date,
                merchant_name=merchant_name,
                tax_id=tax_id,
                expense_category=expense_category,
                subtotal=subtotal,
                discount_amount=discount,
                vat_amount=vat_amount,
                net_amount=net_amount,
                has_wht=has_wht,
                wht_rate=wht_rate,
                wht_amount=wht_amount,
                payment_method=payment_method,
                source_filename=original_filename,
                created_at=now_str,
                created_by=created_by
            )
            session.add(receipt)
            session.flush()

            # 5. Save Details (line items)
            for item in doc_payload.get("items", []):
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
        logger.error(f"Failed to insert relational receipt for document '{document_id}': {e}")
        return False


def get_receipt_by_document_id(document_id: str) -> dict | None:
    """Retrieves an expense receipt and its line items by document_id."""
    try:
        with get_db_session() as session:
            receipt = session.scalars(select(ExpenseReceipt).filter_by(document_id=document_id)).first()
            if not receipt:
                return None
            receipt_dict = receipt.to_dict()
            items = session.scalars(select(ExpenseReceiptItem).filter_by(receipt_id=receipt.receipt_id)).all()
            receipt_dict["items"] = [item.to_dict() for item in items]
            return receipt_dict
    except Exception as e:
        logger.error(f"Failed to get receipt for document '{document_id}': {e}")
        return None
