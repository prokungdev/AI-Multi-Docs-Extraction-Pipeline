"""Express accounting format output exporter using SQLAlchemy 2.0 ORM."""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import pandas as pd
from sqlalchemy import select, func
from .base import BaseOutputExporter
from src.infrastructure.database import get_db_session, DocumentControl
from src.infrastructure.core.constants import DocumentStatusCode, DefaultIdentifier


class ExpressExpenseExporter(BaseOutputExporter):
    """
    Dedicated exporter for exporting approved documents to the Express accounting system format.
    Handles account code mappings, consolidated row formats, and custom voucher running numbers.
    """
    display_name = "Express Accounting (PV Voucher with Running Number)"
    has_custom_params = True
    encoding = "cp874"

    # Default fallback account code mapping
    DEFAULT_ACCOUNT_MAPPING = {
        DefaultIdentifier.NO_TAX_ID: {"acc_code": "5999-99", "desc": "Miscellaneous Expense"}
    }

    def get_next_sequence_number(self) -> int:
        """
        Retrieves the next voucher sequence number by counting APPROVED documents using SQLAlchemy ORM.
        """
        try:
            with get_db_session() as session:
                stmt = select(func.count()).select_from(DocumentControl).where(
                    DocumentControl.status_code == DocumentStatusCode.APPROVED,
                    DocumentControl.doc_type_id == self.doc_type_id
                )
                count = session.scalars(stmt).one()
                return count + 1
        except Exception:
            return 1

    def generate_running_number(self, prefix: Optional[str], current_index: int, start_no: int = 1, doc_date: Optional[str] = None) -> str:
        """
        Formats custom running number string, e.g. PV2608-0001 or PV-0001.
        """
        seq = start_no + current_index
        if prefix:
            return f"{prefix}{seq:04d}"
        
        # Default PVYYMM-XXXX format
        yymm = "2608"
        if doc_date and len(doc_date) >= 7:
            # Parse YYYY-MM
            try:
                parts = doc_date.replace("/", "-").split("-")
                if len(parts) >= 2 and len(parts[0]) == 4:
                    yymm = f"{parts[0][-2:]}{parts[1].zfill(2)}"
            except Exception:
                pass
        return f"PV{yymm}-{seq:04d}"

    def transform(self, approved_docs: List[Dict[str, Any]], **kwargs) -> pd.DataFrame:
        """
        Transforms approved documents into standard Express PV format rows.
        """
        prefix = kwargs.get("prefix")
        start_no = kwargs.get("start_voucher_no") or kwargs.get("start_no")
        if start_no is None:
            start_no = self.get_next_sequence_number()

        rows = []
        for idx, doc in enumerate(approved_docs):
            payload = doc.get("payload") or doc.get("data_payload") or doc
            receipt_info = payload.get("receipt_info", {}) if isinstance(payload, dict) else {}
            merchant_obj = payload.get("merchant", {}) if isinstance(payload, dict) else {}
            totals_obj = payload.get("totals", {}) if isinstance(payload, dict) else {}

            date_str = doc.get("doc_date") or receipt_info.get("transaction_date", "")
            doc_number = doc.get("doc_number") or receipt_info.get("receipt_number", "")
            merchant_name = doc.get("entity_name") or merchant_obj.get("name", "") or payload.get("merchant_name", "")
            tax_id = doc.get("tax_id") or merchant_obj.get("tax_id", "") or payload.get("tax_id", "")
            
            subtotal = float(doc.get("subtotal", 0.0) or totals_obj.get("subtotal", 0.0))
            vat_amount = float(doc.get("vat_amount", 0.0) or totals_obj.get("vat_amount", 0.0))
            discount = float(doc.get("discount", 0.0) or totals_obj.get("discount", 0.0))
            net_amount = float(doc.get("total_amount", 0.0) or totals_obj.get("net_amount", 0.0))

            voucher_no = self.generate_running_number(prefix, idx, start_no=int(start_no), doc_date=date_str)

            rows.append({
                "Voucher_No": voucher_no,
                "Doc_Date": date_str,
                "Doc_Number": doc_number,
                "Merchant_Name": merchant_name,
                "Tax_ID": tax_id,
                "Subtotal": subtotal,
                "Vat_Amount": vat_amount,
                "Discount": discount,
                "Net_Amount": net_amount,
                "Account_Code": "5999-99",
                "Department": "HQ",
            })

        return pd.DataFrame(rows)
