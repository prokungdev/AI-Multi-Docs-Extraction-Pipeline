"""Expense Receipt Document Type Definition."""

from src.infrastructure.core.constants import DocTypeId
from .base import BaseDocType


class ExpenseReceiptDocType(BaseDocType):
    """Expense Receipt (ใบเสร็จรับเงินค่าใช้จ่าย) Document Type."""

    doc_type_id = DocTypeId.EXPENSE_RECEIPT
    display_name = "ใบเสร็จรับเงินค่าใช้จ่าย (Expense Receipt)"
    description = "ใบเสร็จรับเงินสำหรับบันทึกค่าใช้จ่ายทั่วไป"
    sort_order = 1
    is_active = True

