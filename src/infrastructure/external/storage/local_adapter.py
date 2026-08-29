"""Local Filesystem Storage Adapter.

Implements BaseStorageAdapter for local OS filesystem operations with atomic safety.
"""

import os
import json
import shutil
from typing import Optional, List, Any
from PIL import Image
from src.infrastructure.core.logger import logger
from .base import BaseStorageAdapter


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
        """Reads and deserializes JSON from local file."""
        norm_path = self._normalize(path)
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Storage JSON file not found: {norm_path}")
        with open(norm_path, "r", encoding=encoding) as f:
            return json.load(f)

    def write_json(self, path: str, data: Any, encoding: str = "utf-8", indent: int = 2) -> bool:
        """Serializes and writes JSON to local file."""
        norm_path = self._normalize(path)
        self._ensure_parent_dir(norm_path)
        with open(norm_path, "w", encoding=encoding) as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        return True

    def save_image(self, path: str, image: Image.Image, format: str = "JPEG", quality: int = 85) -> bool:
        """Saves PIL image to local file."""
        norm_path = self._normalize(path)
        self._ensure_parent_dir(norm_path)
        save_kwargs = {"optimize": True}
        if format.upper() in ("JPEG", "JPG", "WEBP"):
            save_kwargs["quality"] = quality
        image.save(norm_path, format=format.upper(), **save_kwargs)
        return True

    def load_image(self, path: str) -> Image.Image:
        """Loads and returns PIL image from local file."""
        norm_path = self._normalize(path)
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Storage image file not found: {norm_path}")
        return Image.open(norm_path)

    def list_files(self, prefix: str, extensions: Optional[List[str]] = None, recursive: bool = True) -> List[str]:
        """Lists files under local directory matching optional extensions."""
        norm_prefix = self._normalize(prefix)
        if not os.path.exists(norm_prefix):
            return []

        matched = []
        clean_exts = [e.lower().lstrip(".") for e in extensions] if extensions else None

        if recursive:
            for root, _, files in os.walk(norm_prefix):
                for f in sorted(files):
                    if clean_exts:
                        ext = os.path.splitext(f)[1].lower().lstrip(".")
                        if ext in clean_exts:
                            matched.append(os.path.join(root, f).replace("\\", "/"))
                    else:
                        matched.append(os.path.join(root, f).replace("\\", "/"))
        else:
            for f in sorted(os.listdir(norm_prefix)):
                full_p = os.path.join(norm_prefix, f).replace("\\", "/")
                if os.path.isfile(full_p):
                    if clean_exts:
                        ext = os.path.splitext(f)[1].lower().lstrip(".")
                        if ext in clean_exts:
                            matched.append(full_p)
                    else:
                        matched.append(full_p)

        return matched

    def exists(self, path: str) -> bool:
        """Checks if local file or directory exists."""
        return os.path.exists(self._normalize(path))

    def delete(self, path: str) -> bool:
        """Deletes local file or directory."""
        norm_path = self._normalize(path)
        if not os.path.exists(norm_path):
            return False
        if os.path.isdir(norm_path):
            shutil.rmtree(norm_path)
        else:
            os.remove(norm_path)
        return True

    def copy(self, src: str, dst: str) -> bool:
        """Copies local file."""
        norm_src = self._normalize(src)
        norm_dst = self._normalize(dst)
        if not os.path.exists(norm_src):
            raise FileNotFoundError(f"Source file not found: {norm_src}")
        self._ensure_parent_dir(norm_dst)
        shutil.copy2(norm_src, norm_dst)
        return True

    def move(self, src: str, dst: str) -> bool:
        """Moves local file."""
        norm_src = self._normalize(src)
        norm_dst = self._normalize(dst)
        if not os.path.exists(norm_src):
            raise FileNotFoundError(f"Source file not found: {norm_src}")
        self._ensure_parent_dir(norm_dst)
        shutil.move(norm_src, norm_dst)
        return True

    copy_file = copy
    move_file = move
    delete_file = delete

