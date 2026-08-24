"""Express accounting format output exporter using SQLAlchemy 2.0 ORM."""

from typing import List, Dict, Any
import pandas as pd
from sqlalchemy import select, func
from .base import BaseOutputExporter
from src.core.db import get_db_session, Document
from src.core.constants import DocumentStatusCode, DefaultIdentifier


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
                stmt = select(func.count()).select_from(Document).where(
                    Document.status_code == DocumentStatusCode.APPROVED,
                    Document.domain_id == self.domain_id
                )
                count = session.scalars(stmt).one()
                return count + 1
        except Exception:
            return 1

    def generate_running_number(self, prefix: str, current_index: int, start_no: int = 1) -> str:
        """
        Generates a running voucher number like PV2608-0001.
        """
        seq = start_no + current_index
        return f"{prefix}{seq:04d}"

    def transform(self, approved_docs: List[Dict[str, Any]], **kwargs) -> pd.DataFrame:
        """
        Transforms approved documents into the Express ledger format.
        Supported kwargs:
          - start_voucher_no: int (default: resolved sequence number)
          - voucher_prefix: str (default: "PV2608-")
        """
        start_no = kwargs.get("start_voucher_no")
        if start_no is None:
            start_no = self.get_next_sequence_number()

        prefix = kwargs.get("voucher_prefix", "PV2608-")

        rows = []
        for idx, doc in enumerate(approved_docs):
            voucher_no = self.generate_running_number(prefix, idx, start_no)
            source_id = doc.get("source_id", DefaultIdentifier.NO_TAX_ID)

            mapping = self.DEFAULT_ACCOUNT_MAPPING.get(
                source_id,
                self.DEFAULT_ACCOUNT_MAPPING[DefaultIdentifier.NO_TAX_ID]
            )

            # Resolve financial values
            subtotal = float(doc.get("total_amount") or 0.0)
            vat_amount = 0.0
            discount = 0.0
            net_amount = subtotal

            if "data_payload" in doc and isinstance(doc["data_payload"], dict):
                totals = doc["data_payload"].get("totals") or doc["data_payload"].get("financial_summary") or {}
                subtotal = float(totals.get("subtotal") or subtotal)
                vat_amount = float(totals.get("vat_amount") or 0.0)
                discount = float(totals.get("discount") or 0.0)
                net_amount = float(totals.get("net_amount") or subtotal)

            rows.append({
                "Voucher_No": voucher_no,
                "Doc_Date": doc.get("doc_date", doc.get("transaction_date", "")),
                "Original_Doc_No": doc.get("doc_number", ""),
                "Merchant_Name": doc.get("entity_name", doc.get("merchant_name", "")),
                "Tax_ID": doc.get("tax_id", ""),
                "Account_Code": mapping["acc_code"],
                "Description": mapping["desc"],
                "Subtotal": subtotal,
                "VAT_Amount": vat_amount,
                "Discount": discount,
                "Net_Amount": net_amount
            })

        return pd.DataFrame(rows)
