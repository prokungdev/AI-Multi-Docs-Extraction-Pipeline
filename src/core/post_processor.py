import os
import json
import re
import logging
from datetime import datetime

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger("post_processor")

def load_source_rules(domain: str, source: str, configs_dir: str = "configs") -> dict:
    """
    Loads rules.json for a specific merchant source.
    """
    rules_path = os.path.join(configs_dir, "domains", domain, "sources", source, "rules.json")
    if os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading source rules for '{source}' in domain '{domain}': {e}")
    
    # Fallback to _default rules
    default_rules_path = os.path.join(configs_dir, "domains", domain, "sources", "_default", "rules.json")
    if os.path.exists(default_rules_path):
        try:
            with open(default_rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading default source rules: {e}")
            
    return {}

def normalize_date_to_ad(date_str: str, source_era: str = "BE") -> str:
    """
    Converts Buddhist Era (BE/พ.ศ.) years (> 2500) to Christian Era (AD/ค.ศ.) in YYYY-MM-DD format.
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

def apply_source_rules(payload: dict, domain: str, source: str) -> tuple[dict, bool, str | None]:
    """
    Applies source-specific post-processing rules onto extracted JSON payload.
    
    Returns:
        tuple of (updated_payload, requires_review, review_reason)
    """
    if not isinstance(payload, dict):
        return payload, False, None

    rules = load_source_rules(domain, source)
    post_rules = rules.get("post_processing_rules", {})
    allowed_tax_ids = [t.replace(" ", "").replace("-", "") for t in rules.get("tax_ids", []) if t]
    
    requires_review = False
    review_reasons = []

    # 1. Tax ID Verification
    merchant_obj = payload.get("merchant", {})
    extracted_tax_id = merchant_obj.get("tax_id") or payload.get("tax_id", "")
    clean_extracted_tax_id = extracted_tax_id.replace(" ", "").replace("-", "").strip() if extracted_tax_id else ""

    if source != "_default" and allowed_tax_ids:
        if not clean_extracted_tax_id:
            requires_review = True
            review_reasons.append(f"ไม่พบเลขประจำตัวผู้เสียภาษีผู้ขายในเอกสาร (ต้องการ Tax ID ของ '{source}')")
        elif clean_extracted_tax_id not in allowed_tax_ids:
            requires_review = True
            review_reasons.append(
                f"เลขประจำตัวผู้เสียภาษีผู้ขาย ('{extracted_tax_id}') ไม่ตรงกับรายการ Tax ID ที่ได้รับอนุมัติในกฎของ '{source}'"
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
