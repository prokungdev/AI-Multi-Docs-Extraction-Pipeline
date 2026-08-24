"""
Multi-tenant storage infrastructure with Adapter Pattern abstraction.
"""

from src.infrastructure.storage.base import BaseStorageAdapter  # noqa: F401
from src.infrastructure.storage.local_adapter import LocalStorageAdapter  # noqa: F401
from src.infrastructure.storage.storage_manager import StoragePathManager, storage_manager  # noqa: F401
