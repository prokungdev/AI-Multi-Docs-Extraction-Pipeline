"""
Integration test suite for StoragePathManager — Empty Staging Folder Cleanup.
Tests real filesystem operations via StoragePathManager + LocalStorageAdapter.
Requires integration test DB setup (schema + seed) from conftest.py.
"""

import os
import pytest

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
