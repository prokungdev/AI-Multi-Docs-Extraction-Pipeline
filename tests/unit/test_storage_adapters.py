"""
Unit Tests for Storage Adapters and Storage Abstraction Layer.
Validates LocalStorageAdapter CRUD, Image/JSON handling, atomic safety, and directory management.
"""

import os
import shutil
import tempfile
import unittest
import uuid
from PIL import Image

from src.infrastructure.storage.base import BaseStorageAdapter
from src.infrastructure.storage.local_adapter import LocalStorageAdapter
from src.infrastructure.storage.storage_manager import StoragePathManager, storage_manager


class TestStorageAdapters(unittest.TestCase):
    """
    Unit test suite for LocalStorageAdapter and StoragePathManager integration.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_storage_")
        self.adapter = LocalStorageAdapter()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_read_write_text_and_bytes(self):
        """Test reading and writing raw bytes and UTF-8 text."""
        txt_path = os.path.join(self.test_dir, "subdir", "sample.txt")
        bin_path = os.path.join(self.test_dir, "subdir", "sample.bin")

        # 1. Text
        self.adapter.write_text(txt_path, "สวัสดีปีใหม่ 2026")
        self.assertTrue(self.adapter.exists(txt_path))
        content = self.adapter.read_text(txt_path)
        self.assertEqual(content, "สวัสดีปีใหม่ 2026")

        # 2. Bytes
        raw_data = b"\x00\xFF\xAA\x55"
        self.adapter.write_bytes(bin_path, raw_data)
        read_data = self.adapter.read_bytes(bin_path)
        self.assertEqual(read_data, raw_data)

    def test_02_read_write_json(self):
        """Test JSON serialization and deserialization with Unicode support."""
        json_path = os.path.join(self.test_dir, "data", "payload.json")
        sample_payload = {
            "batch_id": "batch_999",
            "merchant_name": "ร้านสะดวกซื้อ",
            "items": [{"name": "นมสด", "price": 45.5}]
        }

        self.adapter.write_json(json_path, sample_payload)
        self.assertTrue(self.adapter.exists(json_path))

        loaded = self.adapter.read_json(json_path)
        self.assertEqual(loaded["merchant_name"], "ร้านสะดวกซื้อ")
        self.assertEqual(len(loaded["items"]), 1)
        self.assertEqual(loaded["items"][0]["price"], 45.5)

    def test_03_save_load_image(self):
        """Test saving and loading PIL images in JPEG format."""
        img_path = os.path.join(self.test_dir, "images", "doc_page.jpg")
        img = Image.new("RGB", (100, 100), color="blue")

        self.adapter.save_image(img_path, img, format="JPEG", quality=90)
        self.assertTrue(self.adapter.exists(img_path))

        loaded_img = self.adapter.load_image(img_path)
        self.assertEqual(loaded_img.size, (100, 100))
        self.assertEqual(loaded_img.format, "JPEG")

    def test_04_list_files_and_filtering(self):
        """Test listing files with extension filtering and recursive walking."""
        sub = os.path.join(self.test_dir, "tree", "level1")
        self.adapter.write_text(os.path.join(sub, "f1.pdf"), "dummy pdf")
        self.adapter.write_text(os.path.join(sub, "f2.jpg"), "dummy jpg")
        self.adapter.write_text(os.path.join(sub, "f3.png"), "dummy png")
        self.adapter.write_text(os.path.join(sub, "f4.txt"), "dummy txt")

        # 1. Filter by PDF only
        pdfs = self.adapter.list_files(self.test_dir, extensions=["pdf"])
        self.assertEqual(len(pdfs), 1)
        self.assertTrue(pdfs[0].endswith("f1.pdf"))

        # 2. Filter by images
        images = self.adapter.list_files(self.test_dir, extensions=["jpg", "png"])
        self.assertEqual(len(images), 2)

        # 3. List all files
        all_files = self.adapter.list_files(self.test_dir)
        self.assertEqual(len(all_files), 4)

    def test_05_copy_move_and_delete(self):
        """Test copying, moving, and deleting files."""
        src_path = os.path.join(self.test_dir, "source.txt")
        copy_dst = os.path.join(self.test_dir, "copied", "target.txt")
        move_dst = os.path.join(self.test_dir, "moved", "target.txt")

        self.adapter.write_text(src_path, "Original content")

        # Copy
        self.adapter.copy_file(src_path, copy_dst)
        self.assertTrue(self.adapter.exists(src_path))
        self.assertTrue(self.adapter.exists(copy_dst))
        self.assertEqual(self.adapter.read_text(copy_dst), "Original content")

        # Move
        self.adapter.move_file(src_path, move_dst)
        self.assertFalse(self.adapter.exists(src_path))
        self.assertTrue(self.adapter.exists(move_dst))
        self.assertEqual(self.adapter.read_text(move_dst), "Original content")

        # Delete
        self.adapter.delete(copy_dst)
        self.assertFalse(self.adapter.exists(copy_dst))

    def test_06_missing_file_raises_filenotfound(self):
        """Test reading non-existent files raises explicit FileNotFoundError."""
        bad_path = os.path.join(self.test_dir, "nonexistent.json")
        with self.assertRaises(FileNotFoundError):
            self.adapter.read_text(bad_path)
        with self.assertRaises(FileNotFoundError):
            self.adapter.load_image(bad_path)

    def test_07_storage_manager_adapter_binding(self):
        """Test StoragePathManager exposes LocalStorageAdapter."""
        manager = StoragePathManager()
        self.assertIsInstance(manager.adapter, BaseStorageAdapter)
        self.assertIsInstance(manager.adapter, LocalStorageAdapter)


if __name__ == "__main__":
    unittest.main()
