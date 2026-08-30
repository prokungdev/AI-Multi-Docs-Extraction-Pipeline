"""Express Accounting Destination Target Adapter (OE Screen RPA / Bot).

Translates Canonical Journal Voucher and Expense Receipt models into the exact
JSON schema for UiPath RPA automation into Express OE (Other Expenses) screen.

Key Features & Business Rules:
- Converts ISO CE dates (YYYY-MM-DD) to Thai Buddhist Era (DD/MM/YY)
- Truncates long invoice reference numbers from tail to 14 characters max
- Maps VatType enum to Express integer codes: EXCLUSIVE -> 2, INCLUSIVE -> 1, NO_VAT -> 0
- Generates Withholding Tax Certificate sequence: YY/MM/NNN (e.g. 26/07/002)
- Supports vendor code lookup and single line / consolidated line summary
"""

from datetime import datetime
from typing import Dict, Any, Optional, List

from src.infrastructure.core.constants import VatType, TargetSystemId
from .base_target_adapter import BaseTargetAdapter


class ExpressTargetAdapter(BaseTargetAdapter):
    """
    Adapter strategy for Express Accounting ERP (OE - Other Expenses screen).
    """
    target_system_id = TargetSystemId.EXPRESS.value
    display_name = "Express Accounting (OE Screen RPA Automation)"

    def format_date(self, iso_date_str: Optional[str]) -> str:
        """
        Converts Common Era ISO date (YYYY-MM-DD) to Thai Buddhist Era (DD/MM/YY).
        Example: '2026-07-30' -> '30/07/69'
        """
        if not iso_date_str:
            return ""

        clean = str(iso_date_str).strip()[:10].replace("/", "-")
        try:
            parts = clean.split("-")
            if len(parts) == 3 and len(parts[0]) == 4:
                year_ce = int(parts[0])
                month = parts[1].zfill(2)
                day = parts[2].zfill(2)
                year_be = year_ce + 543
                yy = str(year_be)[2:4]
                return f"{day}/{month}/{yy}"
            elif len(parts) == 3 and len(parts[2]) == 4:
                day = parts[0].zfill(2)
                month = parts[1].zfill(2)
                year_ce = int(parts[2])
                year_be = year_ce + 543
                yy = str(year_be)[2:4]
                return f"{day}/{month}/{yy}"
        except Exception:
            pass

        return clean

    def truncate_ref_bill_no(self, raw_ref_no: Optional[str]) -> str:
        """
        Express RefBillNo constraint: maximum 14 characters.
        Truncates from the tail (right-most characters) if length exceeds 14.
        """
        if not raw_ref_no:
            return ""
        clean_ref = str(raw_ref_no).strip()
        if len(clean_ref) > 14:
            return clean_ref[-14:]
        return clean_ref

    def map_vat_type_id(self, vat_type: Optional[str]) -> int:
        """
        Maps canonical VatType to Express OE VatTypeId:
        - EXCLUSIVE -> 2 (แยกนอก)
        - INCLUSIVE -> 1 (รวมใน)
        - NO_VAT -> 0 (ไม่มีภาษี / ได้รับการยกเว้น)
        """
        if not vat_type:
            return 2  # Default to EXCLUSIVE (2)
        
        normalized = str(vat_type).strip().upper()
        if normalized in (VatType.EXCLUSIVE.value, "EXCLUSIVE", "2"):
            return 2
        elif normalized in (VatType.INCLUSIVE.value, "INCLUSIVE", "1"):
            return 1
        elif normalized in (VatType.NO_VAT.value, "NO_VAT", "ZERO_VAT", "0"):
            return 0
        return 2

    def generate_withholding_tax_no(
        self,
        voucher_no: Optional[str],
        voucher_date: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generates Express Withholding Tax No in format: YY/MM/NNN
        Example: For voucher 'OE260730002', returns '26/07/002'
        """
        if not voucher_no:
            return None

        clean_vch = str(voucher_no).strip()
        # Expected format OE{YY}{MM}{DD}{SEQ:03d}, e.g. OE260730002
        if len(clean_vch) >= 11 and clean_vch.startswith("OE"):
            yy = clean_vch[2:4]
            mm = clean_vch[4:6]
            seq = clean_vch[-3:]
            return f"{yy}/{mm}/{seq}"

        # Fallback to voucher_date if non-standard voucher_no
        if voucher_date and len(voucher_date) >= 7:
            try:
                dt = datetime.strptime(voucher_date.strip()[:10], "%Y-%m-%d")
                yy = str(dt.year)[2:4]
                mm = f"{dt.month:02d}"
                seq = clean_vch[-3:] if len(clean_vch) >= 3 else "001"
                return f"{yy}/{mm}/{seq}"
            except Exception:
                pass

        return None

    def transform_voucher(
        self,
        voucher: Dict[str, Any],
        merchant_config: Optional[Dict[str, Any]] = None,
        account_mapping: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Transforms canonical JournalVoucher data into Express OE Screen JSON.
        """
        voucher_no = voucher.get("voucher_no") or ""
        voucher_date_iso = voucher.get("voucher_date") or ""
        ref_doc_no = voucher.get("ref_doc_no") or ""
        ref_doc_date_iso = voucher.get("ref_doc_date") or voucher_date_iso

        formatted_vch_date = self.format_date(voucher_date_iso)
        formatted_ref_date = self.format_date(ref_doc_date_iso)
        truncated_ref_no = self.truncate_ref_bill_no(ref_doc_no)

        vat_type = voucher.get("vat_type") or (merchant_config.get("default_vat_type") if merchant_config else "EXCLUSIVE")
        vat_type_id = self.map_vat_type_id(vat_type)

        vendor_code = (
            voucher.get("vendor_code")
            or (merchant_config.get("vendor_code") if merchant_config else "")
            or "MISC"
        )

        vendor_name = (
            voucher.get("vendor_name")
            or (merchant_config.get("merchant_name") if merchant_config else "")
            or ""
        )

        subtotal = round(float(voucher.get("subtotal_amount", 0.0)), 2)
        vat_rate = round(float(voucher.get("vat_rate", 7.0)), 2)
        vat_amount = round(float(voucher.get("vat_amount", 0.0)), 2)
        wht_amount = round(float(voucher.get("wht_amount", 0.0)), 2)
        net_amount = round(float(voucher.get("net_amount", 0.0)), 2)

        # WHT Details
        has_wht = 1 if wht_amount > 0 or (merchant_config and merchant_config.get("has_wht")) else 0
        wht_rate = 0.0
        wht_no = None

        if has_wht:
            wht_rate = float(
                voucher.get("wht_rate")
                or (merchant_config.get("default_wht_rate") if merchant_config else 0.0)
                or 0.0
            )
            wht_no = self.generate_withholding_tax_no(voucher_no, voucher_date_iso)

        # Transform line items
        raw_items = voucher.get("items") or []
        express_lines: List[Dict[str, Any]] = []

        if raw_items:
            for item in raw_items:
                acc_code = item.get("account_code") or (account_mapping.get("account_code") if account_mapping else "5999-99")
                amt = round(float(item.get("amount", subtotal)), 2)
                desc = item.get("description") or f"{vendor_name} ({formatted_vch_date})".strip()

                express_lines.append({
                    "account_code": acc_code,
                    "amount": amt,
                    "description": desc,
                })
        else:
            # Fallback single summary line
            acc_code = account_mapping.get("account_code") if account_mapping else "5999-99"

            express_lines.append({
                "account_code": acc_code,
                "amount": subtotal,
                "description": f"{vendor_name} ({formatted_vch_date})".strip(),
            })

        is_override_vat = int(
            voucher.get("is_override_vat")
            if voucher.get("is_override_vat") is not None
            else (merchant_config.get("is_override_vat", 1) if merchant_config else 1)
        )

        express_payload = {
            "voucher_no": voucher_no,
            "voucher_date": formatted_vch_date,
            "vendor_code": vendor_code,
            "ref_bill_no": truncated_ref_no,
            "ref_bill_date": formatted_ref_date,
            "vat_type_id": vat_type_id,
            "subtotal": subtotal,
            "vat_amount": vat_amount,
            "is_override_vat": is_override_vat,
            "wht_no": wht_no,
            "wht_rate": wht_rate if has_wht else 0.0,
            "wht_amount": wht_amount if has_wht else 0.0,
            "lines": express_lines,
        }

        return express_payload
