"""
Domain Service: Post-Processing, Date Normalization & Business Financial Balancing.
100% Pure Domain Logic (In-Memory, zero external database or disk I/O coupling).
"""

import re
from typing import Optional, Tuple, List, Dict, Any


def normalize_date_to_ad(date_str: str, source_era: str = "BE") -> str:
    """
    Converts Buddhist Era (BE) years (> 2500) to Christian Era (AD) in YYYY-MM-DD format.
    Pure string manipulation and regex algorithm.
    """
    if not date_str or not isinstance(date_str, str):
        return ""
        
    clean_date = date_str.strip()
    
    # Pattern 1: YYYY-MM-DD or YYYY/MM/DD
    m1 = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", clean_date)
    if m1:
        year = int(m1.group(1))
        month = int(m1.group(2))
        day = int(m1.group(3))
        if year > 2500:
            year -= 543
        return f"{year:04d}-{month:02d}-{day:02d}"
        
    # Pattern 2: DD/MM/YYYY or DD-MM-YYYY
    m2 = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", clean_date)
    if m2:
        day = int(m2.group(1))
        month = int(m2.group(2))
        year = int(m2.group(3))
        if year > 2500:
            year -= 543
        return f"{year:04d}-{month:02d}-{day:02d}"
        
    return clean_date


def apply_source_rules(
    payload: dict,
    doc_type: str = "expense_receipt",
    source: str = None,
    rules: Optional[dict] = None
) -> Tuple[dict, bool, Optional[str]]:
    """
    Applies business rules onto extracted JSON payload in-memory.
    Normalizes dates, verifies Tax ID adherence, and sets default categories.
    """
    if not isinstance(payload, dict):
        return payload, False, None

    post_rules = (rules or {}).get("post_processing_rules", {})
    allowed_tax_ids = [t.replace(" ", "").replace("-", "") for t in (rules or {}).get("tax_ids", []) if t]
    
    requires_review = False
    review_reasons = []

    # 1. Tax ID Verification
    merchant_obj = payload.get("merchant", {})
    extracted_tax_id = merchant_obj.get("tax_id") or payload.get("tax_id", "")
    clean_extracted_tax_id = extracted_tax_id.replace(" ", "").replace("-", "").strip() if extracted_tax_id else ""

    if source not in ("NO_TAXID", "NO_TAX_LABEL", None) and allowed_tax_ids:
        if not clean_extracted_tax_id:
            requires_review = True
            review_reasons.append(f"Seller Tax ID not found in document (Required Tax ID for '{source}')")
        elif clean_extracted_tax_id not in allowed_tax_ids:
            requires_review = True
            review_reasons.append(
                f"Seller Tax ID ('{extracted_tax_id}') does not match approved Tax IDs for '{source}'"
            )

    # 2. Date Normalization (BE -> AD)
    date_rules = post_rules.get("date_rules", {})
    source_era = date_rules.get("source_era", "BE")
    
    receipt_info = payload.get("receipt_info", {})
    raw_date = receipt_info.get("transaction_date") or payload.get("transaction_date", "")
    if raw_date:
        normalized_date = normalize_date_to_ad(raw_date, source_era=source_era)
        if isinstance(payload.get("receipt_info"), dict):
            payload["receipt_info"]["transaction_date"] = normalized_date
        payload["transaction_date"] = normalized_date

    # 3. Expense Category Code & Financial Defaults
    expense_rules = post_rules.get("expense_rules", {})
    default_cat_code = expense_rules.get("expense_category_code", "GENERAL_EXPENSE")
    
    if isinstance(payload.get("receipt_info"), dict):
        if not payload["receipt_info"].get("expense_category_code"):
            payload["receipt_info"]["expense_category_code"] = default_cat_code

    # 4. Item Defaults (unit, currency)
    item_rules = post_rules.get("item_rules", {})
    default_unit = item_rules.get("default_unit", "")
    default_currency = item_rules.get("default_currency", "")

    items = payload.get("items", [])
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                if not item.get("unit"):
                    item["unit"] = default_unit

    totals_obj = payload.get("totals", {})
    if isinstance(totals_obj, dict):
        if not totals_obj.get("currency"):
            totals_obj["currency"] = default_currency
        payload["totals"] = totals_obj

    # Attach Post-Processing Meta
    payload["_post_processing_meta"] = {
        "source_matched": source,
        "expense_category_code": default_cat_code,
        "default_wht_rate": expense_rules.get("default_wht_rate", 0.0),
        "default_vat_rate": post_rules.get("tax_rules", {}).get("default_vat_rate", 7.0),
        "requires_review": requires_review,
        "review_reasons": review_reasons
    }

    review_reason_str = " | ".join(review_reasons) if review_reasons else None
    return payload, requires_review, review_reason_str


def validate_financial_math(payload: dict, tolerance: float = 0.05) -> Tuple[bool, List[str]]:
    """
    Validates financial math balance:
    1. Subtotal - Discount + VAT == Net Amount
    2. Sum(Items) == Subtotal
    Returns: (is_discrepant, discrepancy_notes)
    """
    fin = payload.get("totals") or payload.get("financial_summary", {})
    subtotal = float(fin.get("subtotal", 0.0))
    discount = float(fin.get("discount", 0.0))
    vat_amount = float(fin.get("vat_amount", 0.0))
    net_amount = float(fin.get("net_amount", 0.0))
    
    calculated_net = subtotal - discount + vat_amount
    net_discrepancy = abs(calculated_net - net_amount) > tolerance
    
    items = payload.get("items", [])
    item_sum = sum(float(item.get("total_price", 0.0)) for item in items if isinstance(item, dict))
    items_discrepancy = (item_sum > 0) and (abs(item_sum - subtotal) > tolerance)
    
    discrepancy_notes = []
    if net_discrepancy:
        discrepancy_notes.append("Financial formula mismatch (Subtotal - Discount + VAT != Net)")
    if items_discrepancy:
        discrepancy_notes.append("Item sum does not match subtotal before discount (Sum items != Subtotal)")
        
    is_discrepant = bool(net_discrepancy or items_discrepancy)
    return is_discrepant, discrepancy_notes


def evaluate_review_priority(
    overall_confidence: float = 0.70,
    is_blurry: bool = False,
    has_ambiguous_fields: bool = False,
    is_complete: bool = True
) -> str:
    """
    Calculates review priority category (HIGH, MEDIUM, LOW) based on confidence thresholds and quality flags.
    """
    if overall_confidence < 0.60 or is_blurry or has_ambiguous_fields or not is_complete:
        return "HIGH"
    elif overall_confidence < 0.85:
        return "MEDIUM"
    return "LOW"
