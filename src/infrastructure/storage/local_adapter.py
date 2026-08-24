"""
Local Filesystem Storage Adapter.
Implements BaseStorageAdapter for local OS filesystem operations with atomic safety.
"""

import os
import json
import shutil
from typing import Optional, List, Any
from PIL import Image
from src.infrastructure.common.logger import logger
from src.infrastructure.storage.base import BaseStorageAdapter


class LocalStorageAdapter(BaseStorageAdapter):
    """
    Concrete implementation of BaseStorageAdapter for local disk filesystems.
    Auto-creates directories and handles path normalization on Windows/Linux.
    """

    def _normalize(self, path: str) -> str:
        """Normalizes file path using forward slashes."""
        return str(path).replace("\\", "/")

    def _ensure_parent_dir(self, path: str) -> None:
        """Ensures the parent directory exists."""
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def read_bytes(self, path: str) -> bytes:
        """Reads raw binary bytes from local file."""
        norm_path = self._normalize(path)
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Storage file not found: {norm_path}")
        with open(norm_path, "rb") as f:
            return f.read()

    def write_bytes(self, path: str, data: bytes) -> bool:
        """Writes raw binary bytes to local file."""
        norm_path = self._normalize(path)
        self._ensure_parent_dir(norm_path)
        with open(norm_path, "wb") as f:
            f.write(data)
        return True

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Reads text content from local file."""
        norm_path = self._normalize(path)
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Storage file not found: {norm_path}")
        with open(norm_path, "r", encoding=encoding) as f:
            return f.read()

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> bool:
        """Writes text content to local file."""
        norm_path = self._normalize(path)
        self._ensure_parent_dir(norm_path)
        with open(norm_path, "w", encoding=encoding) as f:
            f.write(content)
        return True

    def read_json(self, path: str, encoding: str = "utf-8") -> Any:
        """Reads and parses JSON content from local file."""
        text = self.read_text(path, encoding=encoding)
        return json.loads(text)

    def write_json(self, path: str, data: Any, encoding: str = "utf-8", indent: int = 2) -> bool:
        """Serializes and writes JSON content to local file."""
        norm_path = self._normalize(path)
        self._ensure_parent_dir(norm_path)
        with open(norm_path, "w", encoding=encoding) as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        return True

    def save_image(self, path: str, image: Image.Image, format: str = "JPEG", quality: int = 85) -> bool:
        """Saves a PIL Image object to local file."""
        norm_path = self._normalize(path)
        self._ensure_parent_dir(norm_path)
        if format.upper() in ("JPEG", "JPG") and image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        image.save(norm_path, format=format, quality=quality)
        return True

    def load_image(self, path: str) -> Image.Image:
        """Loads and returns a PIL Image object from local file."""
        norm_path = self._normalize(path)
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Image not found at path: {norm_path}")
        return Image.open(norm_path)

    def list_files(self, prefix: str, extensions: Optional[List[str]] = None, recursive: bool = True) -> List[str]:
        """Lists file paths under a directory matching optional extensions."""
        norm_prefix = self._normalize(prefix)
        if not os.path.exists(norm_prefix):
            return []

        clean_exts = [e.lower().lstrip(".") for e in extensions] if extensions else None
        results = []

        if recursive:
            for root, _, files in os.walk(norm_prefix):
                for f in files:
                    if clean_exts:
                        ext = os.path.splitext(f)[1].lower().lstrip(".")
                        if ext not in clean_exts:
                            continue
                    results.append(os.path.join(root, f).replace("\\", "/"))
        else:
            for f in os.listdir(norm_prefix):
                full = os.path.join(norm_prefix, f).replace("\\", "/")
                if os.path.isfile(full):
                    if clean_exts:
                        ext = os.path.splitext(f)[1].lower().lstrip(".")
                        if ext not in clean_exts:
                            continue
                    results.append(full)

        return sorted(results)

    def exists(self, path: str) -> bool:
        """Checks if a file exists on local disk."""
        return os.path.exists(self._normalize(path))

    def delete(self, path: str) -> bool:
        """Deletes a local file if it exists."""
        norm_path = self._normalize(path)
        if os.path.exists(norm_path):
            if os.path.isdir(norm_path):
                shutil.rmtree(norm_path)
            else:
                os.remove(norm_path)
            return True
        return False

    def copy_file(self, src_path: str, dst_path: str) -> bool:
        """Copies a local file to destination path."""
        norm_src = self._normalize(src_path)
        norm_dst = self._normalize(dst_path)
        if not os.path.exists(norm_src):
            raise FileNotFoundError(f"Source file not found: {norm_src}")
        self._ensure_parent_dir(norm_dst)
        shutil.copy2(norm_src, norm_dst)
        return True

    def move_file(self, src_path: str, dst_path: str) -> bool:
        """Moves a local file to destination path."""
        norm_src = self._normalize(src_path)
        norm_dst = self._normalize(dst_path)
        if not os.path.exists(norm_src):
            raise FileNotFoundError(f"Source file not found: {norm_src}")
        self._ensure_parent_dir(norm_dst)
        shutil.move(norm_src, norm_dst)
        return True
