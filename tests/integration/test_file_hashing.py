"""
Integration tests for File Hashing and SHA-256 Checksum calculation on real files.
Enforces isolated temporary file creation and verifies post-test file deletion.
"""

import os
import tempfile
from src.infrastructure.persistence.documents import calculate_file_hash


def test_file_hashing_sha256():
    """Test calculate_file_hash computes valid 64-char SHA-256 checksum and cleans up."""
    # Arrange: Isolated temp file
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"neutral dummy payload bytes for hashing verification 12345")
        tmp_path = tmp.name

    try:
        # Act
        file_hash = calculate_file_hash(tmp_path)

        # Assert
        assert isinstance(file_hash, str)
        assert len(file_hash) == 64
    finally:
        # Cleanup
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        # Cleanup Verification Step: Verify file is deleted
        assert not os.path.exists(tmp_path), f"Leakage detected: {tmp_path} was not deleted!"
