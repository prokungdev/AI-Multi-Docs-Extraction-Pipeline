"""Withholding Tax Document Type Definition."""

from src.infrastructure.core.constants import DocTypeId
from .base import BaseDocType


class WithholdingTaxDocType(BaseDocType):
    """Withholding Tax 50 ทวิ (หนังสือรับรองการหักภาษี ณ ที่จ่าย) Document Type."""

    doc_type_id = DocTypeId.WITHHOLDING_TAX
    display_name = "หนังสือรับรองการหักภาษี ณ ที่จ่าย (Withholding Tax 50 ทวิ)"
    description = "หนังสือรับรองการหักภาษี ณ ที่จ่ายตามมาตรา 50 ทวิ"
    sort_order = 3
    is_active = True
    financial_tolerance = 0.01

