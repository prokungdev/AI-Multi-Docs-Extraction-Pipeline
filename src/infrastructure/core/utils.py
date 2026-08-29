"""Core general utilities."""

from typing import Any, TypeVar, List

T = TypeVar("T")


def chunk_list(items: List[T], size: int) -> List[List[T]]:
    """
    Splits a list into chunks of a given maximum size.
    """
    if size <= 0:
        return [items]
    return [items[i:i + size] for i in range(0, len(items), size)]


def sanitize_tax_id(raw_tax_id: Any) -> str:
    """
    Strips spaces, hyphens, and whitespace to normalize tax ID string.
    Returns empty string if raw_tax_id is None or empty.
    """
    if not raw_tax_id:
        return ""
    return str(raw_tax_id).replace(" ", "").replace("-", "").strip()
