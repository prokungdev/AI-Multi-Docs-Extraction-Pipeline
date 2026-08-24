"""
Domain Service: Merchant Classification Rules, Text Normalization & Sanitization.
100% Pure Domain Logic (In-Memory, zero external database or disk I/O coupling).
"""

import re
from src.infrastructure.common.constants import (
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
