"""
Unit test suite for Empty Staging Folder Cleanup and PipelineProcessLock.
"""

import os
import json
import uuid
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
import pytest

from src.infrastructure.common.process_lock import PipelineProcessLock
from src.infrastructure.storage.storage_manager import StoragePathManager


def test_01_cleanup_empty_staging_folders_only_deletes_empty(tmp_path):
    """Verify that cleanup_empty_staging_folders only deletes empty directories."""
    # Setup test company structure in tmp_path
    test_storage = str(tmp_path).replace("\\", "/")
    sm = StoragePathManager()
    sm.storage_root = test_storage

    comp_code = "C_TEST"
    doc_type = "expense_receipt"

    # Create empty pending folders
    pending_empty_1 = sm.get_raw_data_dir(comp_code, doc_type, status="PENDING", merchant_folder="0105556090377_grab")
    pending_empty_2 = sm.get_raw_data_dir(comp_code, doc_type, status="PENDING", merchant_folder="0105556090377_grabtaxi_thailand")

    # Create non-empty pending folder
    pending_with_file = sm.get_raw_data_dir(comp_code, doc_type, status="PENDING", merchant_folder="0107542000011_cp_all")
    test_file = os.path.join(pending_with_file, "receipt.pdf")
    with open(test_file, "w") as f:
        f.write("dummy pdf content")

    # Create empty ignored folder
    ignored_empty = sm.get_raw_data_dir(comp_code, doc_type, status="IGNORED", merchant_folder="0999999999999_spam")

    assert os.path.exists(pending_empty_1)
    assert os.path.exists(pending_empty_2)
    assert os.path.exists(pending_with_file)
    assert os.path.exists(ignored_empty)

    # Execute cleanup
    removed_count = sm.cleanup_empty_staging_folders(company_code=comp_code, doc_type=doc_type)

    assert removed_count == 3
    assert not os.path.exists(pending_empty_1)
    assert not os.path.exists(pending_empty_2)
    assert not os.path.exists(ignored_empty)
    # The non-empty folder and file MUST be preserved
    assert os.path.exists(pending_with_file)
    assert os.path.exists(test_file)


def test_02_pipeline_process_lock_acquire_and_release(tmp_path):
    """Verify normal lock acquire and release lifecycle."""
    lock_file = str(tmp_path / ".pipeline_test.lock").replace("\\", "/")
    lock = PipelineProcessLock(lock_file_path=lock_file, ttl_seconds=60)

    assert not os.path.exists(lock_file)
    assert lock.acquire() is True
    assert lock.is_acquired is True
    assert os.path.exists(lock_file)

    # Verify content
    with open(lock_file, "r") as f:
        data = json.load(f)
    assert data["pid"] == os.getpid()
    assert "started_at" in data

    assert lock.release() is True
    assert lock.is_acquired is False
    assert not os.path.exists(lock_file)


def test_03_pipeline_process_lock_collision_fails(tmp_path):
    """Verify that a second active process/instance cannot acquire the lock."""
    lock_file = str(tmp_path / ".pipeline_test.lock").replace("\\", "/")
    lock_1 = PipelineProcessLock(lock_file_path=lock_file, ttl_seconds=60)
    lock_2 = PipelineProcessLock(lock_file_path=lock_file, ttl_seconds=60)

    assert lock_1.acquire() is True
    # Lock 2 must fail to acquire
    assert lock_2.acquire() is False
    assert lock_2.is_acquired is False

    # Lock 1 releases -> Lock 2 can now acquire
    assert lock_1.release() is True
    assert lock_2.acquire() is True
    assert lock_2.release() is True


def test_04_pipeline_process_lock_stale_ttl_expiration(tmp_path):
    """Verify that expired lock files beyond TTL are automatically reclaimed."""
    lock_file = str(tmp_path / ".pipeline_test.lock").replace("\\", "/")

    # Simulate stale lock written 2 hours ago
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    payload = {
        "pid": 9999999,
        "started_at": stale_time,
        "metadata": {"test": "stale"}
    }
    with open(lock_file, "w") as f:
        json.dump(payload, f)

    # New lock with 30-min TTL should reclaim stale lock
    lock = PipelineProcessLock(lock_file_path=lock_file, ttl_seconds=1800)
    assert lock.acquire() is True
    assert lock.is_acquired is True

    # Check updated PID
    with open(lock_file, "r") as f:
        data = json.load(f)
    assert data["pid"] == os.getpid()

    assert lock.release() is True


def test_05_pipeline_process_lock_context_manager(tmp_path):
    """Verify context manager semantics for PipelineProcessLock."""
    lock_file = str(tmp_path / ".pipeline_test.lock").replace("\\", "/")

    with PipelineProcessLock(lock_file_path=lock_file, ttl_seconds=60) as lock:
        assert lock.is_acquired is True
        assert os.path.exists(lock_file)

    # After exit, lock should be released
    assert not os.path.exists(lock_file)
    assert lock.is_acquired is False
