"""Base Storage Adapter Interface.

Defines the standard abstract contract for document & asset persistence operations.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from PIL import Image


class BaseStorageAdapter(ABC):
    """
    Abstract Strategy Interface for multi-backend storage systems (Local, S3, MinIO, GCS).
    """

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Reads raw binary bytes from the specified storage path."""
        pass

    @abstractmethod
    def write_bytes(self, path: str, data: bytes) -> bool:
        """Writes raw binary bytes to the specified storage path."""
        pass

    @abstractmethod
    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Reads text string from the specified storage path."""
        pass

    @abstractmethod
    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> bool:
        """Writes text string to the specified storage path."""
        pass

    @abstractmethod
    def read_json(self, path: str, encoding: str = "utf-8") -> Any:
        """Reads and deserializes a JSON payload from storage."""
        pass

    @abstractmethod
    def write_json(self, path: str, data: Any, encoding: str = "utf-8", indent: int = 2) -> bool:
        """Serializes and writes a Python dictionary/list as JSON to storage."""
        pass

    @abstractmethod
    def save_image(self, path: str, image: Image.Image, format: str = "JPEG", quality: int = 85) -> bool:
        """Saves a PIL Image object to the specified path."""
        pass

    @abstractmethod
    def load_image(self, path: str) -> Image.Image:
        """Loads and returns a PIL Image object from the specified path."""
        pass

    @abstractmethod
    def list_files(self, prefix: str, extensions: Optional[List[str]] = None, recursive: bool = True) -> List[str]:
        """Lists file paths matching optional extensions under a folder/prefix."""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Checks if a file or folder exists at path."""
        pass

    @abstractmethod
    def delete(self, path: str) -> bool:
        """Deletes a file or directory at path."""
        pass

    @abstractmethod
    def copy(self, src: str, dst: str) -> bool:
        """Copies file from src to dst."""
        pass

    @abstractmethod
    def move(self, src: str, dst: str) -> bool:
        """Moves file from src to dst."""
        pass
