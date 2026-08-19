from typing import List, Dict, Any
import pandas as pd
from .base import BaseOutputExporter
from src.core.db import get_db_connection

class ExpressExpenseExporter(BaseOutputExporter):
    """
    Dedicated exporter for exporting approved documents to the Express accounting system format.
    Handles account code mappings, consolidated row formats, and custom voucher running numbers.
    """
    display_name = "โปรแกรม Express (บันทึกใบสำคัญจ่าย PV พร้อมรันเลขใหม่)"
    has_custom_params = True
    encoding = "cp874"
    
    # Custom Account Code Mapping for Express
    ACCOUNT_MAPPING = {
        "spx_express": {"acc_code": "5301-02", "desc": "ค่าขนส่งพัสดุ SPX"},
        "grab_thailand": {"acc_code": "5301-01", "desc": "ค่าเดินทาง Grab"},
        "_DEFAULT": {"acc_code": "5999-99", "desc": "ค่าใช้จ่ายเบ็ดเตล็ด"}
    }

    def get_next_sequence_number(self) -> int:
        """
        Retrieves the next voucher sequence number by counting APPROVED documents in SQLite.
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM documents 
                WHERE status_code = 'APPROVED' AND domain_id = ?
            """, (self.domain_id,))
            row = cursor.fetchone()
            count = row[0] if row else 0
            conn.close()
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
            source_id = doc.get("source_id", "_default")
            mapping = self.ACCOUNT_MAPPING.get(source_id, self.ACCOUNT_MAPPING["_DEFAULT"])
            
            # Generate new voucher running number
            voucher_no = self.generate_running_number(prefix, idx, start_no)
            
            financial = doc.get("financial_summary", {})
            subtotal = financial.get("subtotal", doc.get("total_amount", 0.0))
            discount = financial.get("discount", 0.0)
            vat_amount = financial.get("vat_amount", 0.0)
            net_amount = financial.get("net_amount", doc.get("total_amount", 0.0))
            
            # Consolidated row per document
            row = {
                "เลขที่ใบสำคัญ (Voucher)": voucher_no,
                "วันที่ใบสำคัญ": doc.get("doc_date", doc.get("transaction_date", "")),
                "เลขที่บิลเดิม": doc.get("doc_number", ""),
                "ชื่อผู้จำหน่าย": doc.get("entity_name", doc.get("merchant_name", "")),
                "เลขประจำตัวผู้เสียภาษี": doc.get("tax_id", ""),
                "รหัสบัญชี": mapping["acc_code"],
                "คำอธิบาย": mapping["desc"],
                "มูลค่าก่อน VAT": subtotal,
                "ภาษีมูลค่าเพิ่ม": vat_amount,
                "ส่วนลด": discount,
                "ยอดจ่ายสุทธิ": net_amount
            }
            rows.append(row)
            
        return pd.DataFrame(rows)
