import re
from abc import ABC, abstractmethod
from typing import Any

class BaseValidator(ABC):
    """
    Abstract Strategy Interface for Document Data Validation.
    """

    @abstractmethod
    def validate(self, payload: dict, context: dict = None) -> tuple[dict, bool, list[str]]:
        """
        Validates and enriches document payload.
        Returns:
            tuple of (updated_payload, is_invalid_or_needs_review, list_of_warning_reasons)
        """
        pass


class DateNormalizationValidator(BaseValidator):
    """
    Validator Strategy to normalize Buddhist Era (BE) years to Christian Era (AD).
    """

    def validate(self, payload: dict, context: dict = None) -> tuple[dict, bool, list[str]]:
        needs_review = False
        reasons = []
        
        receipt_info = payload.get("receipt_info", {})
        raw_date = receipt_info.get("transaction_date") or payload.get("transaction_date", "")
        
        if raw_date and isinstance(raw_date, str):
            normalized = self._normalize_date(raw_date)
            if isinstance(payload.get("receipt_info"), dict):
                payload["receipt_info"]["transaction_date"] = normalized
            payload["transaction_date"] = normalized

        return payload, needs_review, reasons

    def _normalize_date(self, date_str: str) -> str:
        clean_date = date_str.strip()
        m1 = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", clean_date)
        if m1:
            year, month, day = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
            if year > 2500:
                year -= 543
            return f"{year:04d}-{month:02d}-{day:02d}"
            
        m2 = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", clean_date)
        if m2:
            day, month, year = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
            if year > 2500:
                year -= 543
            return f"{year:04d}-{month:02d}-{day:02d}"
            
        return clean_date


class TaxIDValidator(BaseValidator):
    """
    Validator Strategy for verifying 13-digit Thai Tax Identification Numbers.
    """

    def validate(self, payload: dict, context: dict = None) -> tuple[dict, bool, list[str]]:
        needs_review = False
        reasons = []
        context = context or {}
        merchant_id = context.get("merchant_id") or context.get("source", "NO_TAX_LABEL")
        allowed_tax_ids = context.get("allowed_tax_ids", [])

        merchant_obj = payload.get("merchant", {})
        extracted_tax_id = merchant_obj.get("tax_id") or payload.get("tax_id", "")
        clean_tax_id = str(extracted_tax_id).replace(" ", "").replace("-", "").strip() if extracted_tax_id else ""

        if merchant_id not in ("NO_TAXID", "NO_TAX_LABEL") and allowed_tax_ids:
            if not clean_tax_id:
                needs_review = True
                reasons.append(f"Missing merchant tax ID for merchant '{merchant_id}'")
            elif clean_tax_id not in allowed_tax_ids:
                needs_review = True
                reasons.append(f"Merchant tax ID '{extracted_tax_id}' does not match allowed list for '{merchant_id}'")

        return payload, needs_review, reasons


class FinancialMathValidator(BaseValidator):
    """
    Validator Strategy for checking mathematical consistency of subtotal, discount, VAT, and net amount.
    """

    def validate(self, payload: dict, context: dict = None) -> tuple[dict, bool, list[str]]:
        needs_review = False
        reasons = []

        totals = payload.get("totals", {})
        if isinstance(totals, dict):
            subtotal = float(totals.get("subtotal", 0.0) or 0.0)
            discount = float(totals.get("discount", 0.0) or 0.0)
            vat_amount = float(totals.get("vat_amount", 0.0) or 0.0)
            net_amount = float(totals.get("net_amount", 0.0) or 0.0)

            expected_net = round(subtotal - discount + vat_amount, 2)
            actual_net = round(net_amount, 2)

            if actual_net > 0 and abs(expected_net - actual_net) > 0.05:
                needs_review = True
                reasons.append(f"Financial math mismatch: Subtotal ({subtotal}) - Discount ({discount}) + VAT ({vat_amount}) = {expected_net}, but net_amount is {actual_net}")

        return payload, needs_review, reasons


class ValidationStrategyEngine:
    """
    Strategy Engine to execute a pipeline of validators on extracted payload data.
    """

    def __init__(self, validators: list[BaseValidator] = None):
        self.validators = validators or [
            DateNormalizationValidator(),
            TaxIDValidator(),
            FinancialMathValidator()
        ]

    def run_validation(self, payload: dict, context: dict = None) -> tuple[dict, bool, list[str]]:
        aggregated_payload = payload
        aggregated_needs_review = False
        all_reasons = []

        for validator in self.validators:
            aggregated_payload, needs_review, reasons = validator.validate(aggregated_payload, context)
            if needs_review:
                aggregated_needs_review = True
            all_reasons.extend(reasons)

        return aggregated_payload, aggregated_needs_review, all_reasons
