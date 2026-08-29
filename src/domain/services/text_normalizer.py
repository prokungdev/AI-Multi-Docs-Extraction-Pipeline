"""Domain Service: Text Normalization, Sanitization, and Pure String Formatting.

100% Pure Domain Logic (In-Memory, zero external database or disk I/O coupling).
"""

import re
from typing import Optional
from src.infrastructure.core.constants import (
    PipelineAction,
    DefaultIdentifier,
    MerchantStatusCode,
)


def sanitize_short_name(name: str) -> str:
    """
    Sanitizes a merchant name or identifier into a filesystem-safe short_name.
    Converts to lowercase, removes stop words, replaces non-alphanumeric with underscore.
    """
    if not name or not name.strip():
        return DefaultIdentifier.DEFAULT_SHORT_NAME

    cleaned = name.strip()
    prefixes = [
        "บริษัท", "บจก.", "หจก.", "ห้างหุ้นส่วนจำกัด", "ร้าน", "บมจ.",
        "co.,ltd.", "co., ltd.", "ltd.", "company limited", "corp.", "inc."
    ]
    for p in prefixes:
        pattern = re.compile(re.escape(p), re.IGNORECASE)
        cleaned = pattern.sub("", cleaned).strip()

    cleaned = cleaned.replace(" ", "_")
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '', cleaned)
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')

    if not cleaned:
        cleaned = DefaultIdentifier.DEFAULT_SHORT_NAME

    return cleaned[:35].lower()


def evaluate_merchant_pipeline_action(status_code: str) -> str:
    """
    Maps merchant status code to corresponding pipeline action.
    Pure business policy.
    """
    if status_code == MerchantStatusCode.PENDING:
        return PipelineAction.HOLD
    elif status_code == MerchantStatusCode.IGNORED:
        return PipelineAction.IGNORE
    return PipelineAction.PROCEED


def format_merchant_folder_identifier(tax_id: str, short_name: str) -> str:
    """
    Constructs standardized folder identifier from tax_id and short_name.
    """
    if tax_id and tax_id != DefaultIdentifier.NO_TAX_ID:
        return f"{tax_id}_{short_name or DefaultIdentifier.DEFAULT_SHORT_NAME}"
    return DefaultIdentifier.NO_TAX_ID


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


normalize_thai_date = normalize_date_to_ad


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
