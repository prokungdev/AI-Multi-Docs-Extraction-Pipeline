"""
Domain Service: Post-Processing, Date Normalization & Review Priority.
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
