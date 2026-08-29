"""Multi-tenant Storage Infrastructure (External Layer)."""

from .base import BaseStorageAdapter
from .local_adapter import LocalStorageAdapter
from .storage_manager import StoragePathManager, storage_manager

__all__ = [
    "BaseStorageAdapter",
    "LocalStorageAdapter",
    "StoragePathManager",
    "storage_manager",
]
