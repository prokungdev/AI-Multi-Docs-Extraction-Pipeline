"""Tax Invoice Document Type Definition."""

from src.infrastructure.core.constants import DocTypeId
from .base import BaseDocType


class TaxInvoiceDocType(BaseDocType):
    """Tax Invoice (ใบกำกับภาษีเต็มรูป) Document Type."""

    doc_type_id = DocTypeId.TAX_INVOICE
    display_name = "ใบกำกับภาษีเต็มรูป (Tax Invoice)"
    description = "ใบกำกับภาษีเต็มรูปแบบตามประมวลรัษฎากร"
    sort_order = 2
    is_active = True
    confidence_review = 0.75

