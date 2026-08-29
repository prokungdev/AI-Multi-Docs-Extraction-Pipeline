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


import time
import functools
import threading
from typing import Callable


def _make_hashable(val: Any) -> Any:
    """Recursively converts unhashable objects like dicts and lists to hashable tuples."""
    if isinstance(val, dict):
        return tuple(sorted((k, _make_hashable(v)) for k, v in val.items()))
    elif isinstance(val, (list, set)):
        return tuple(_make_hashable(x) for x in val)
    return val


def ttl_cache(seconds: float = 60.0) -> Callable:
    """
    Thread-safe generic In-Memory Time-To-Live (TTL) caching decorator.
    Attaches .cache_clear() to the wrapped function for explicit cache invalidation.
    """
    def decorator(func: Callable) -> Callable:
        cache: dict[tuple, Any] = {}
        expiry: dict[tuple, float] = {}
        lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = (
                tuple(_make_hashable(a) for a in args),
                tuple(sorted((k, _make_hashable(v)) for k, v in kwargs.items()))
            )
            now = time.monotonic()
            with lock:
                if key in cache and now < expiry.get(key, 0.0):
                    return cache[key]

            result = func(*args, **kwargs)

            with lock:
                cache[key] = result
                expiry[key] = time.monotonic() + seconds
            return result

        def cache_clear():
            with lock:
                cache.clear()
                expiry.clear()

        wrapper.cache_clear = cache_clear
        return wrapper

    return decorator

