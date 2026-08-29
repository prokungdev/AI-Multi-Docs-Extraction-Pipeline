"""Base Strategy Interface for Destination ERP & Target System Adapters.

Provides extensible abstraction for converting Canonical Financial Entities
(JournalVoucher, JournalVoucherItem, ExpenseReceipt) into destination-specific
RPA Bot / API Gateway payloads (e.g. Express OE Screen, SAP, PEAK, HR Portal).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class BaseTargetAdapter(ABC):
    """
    Abstract Strategy class for Destination ERP Target Adapters.
    """
    target_system_id: str = ""
    display_name: str = ""

    def __init__(self):
        if not self.display_name:
            self.display_name = self.__class__.__name__

    @abstractmethod
    def format_date(self, iso_date_str: Optional[str]) -> str:
        """
        Converts standard ISO Common Era date string (YYYY-MM-DD) into destination format.
        Must be implemented by concrete adapters.
        """
        pass

    @abstractmethod
    def transform_voucher(
        self,
        voucher: Dict[str, Any],
        merchant_config: Optional[Dict[str, Any]] = None,
        account_mapping: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Transforms a Canonical Journal Voucher dictionary and child items into the
        exact JSON payload expected by the destination ERP or RPA worker.
        """
        pass

    @abstractmethod
    def generate_withholding_tax_no(
        self,
        voucher_no: Optional[str],
        voucher_date: Optional[str],
    ) -> Optional[str]:
        """
        Generates destination-specific Withholding Tax certificate sequence if applicable.
        """
        pass
