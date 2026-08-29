"""
Unit tests for String Sanitization and List Chunking utilities.
Pure helper function testing without side effects.
"""

import pytest
from src.infrastructure.core.utils import chunk_list
from src.infrastructure.database.repositories import sanitize_short_name


# ==============================================================================
# List Chunking Utility Tests
# ==============================================================================

@pytest.mark.parametrize("input_list, chunk_sz, expected", [
    ([1, 2, 3, 4, 5, 6], 2, [[1, 2], [3, 4], [5, 6]]),
    (["a", "b", "c", "d", "e"], 2, [["a", "b"], ["c", "d"], ["e"]]),
    ([], 5, []),
    ([1, 2, 3], 0, [[1, 2, 3]]),
    ([1, 2, 3], -1, [[1, 2, 3]]),
])
def test_list_chunking_parameterized(input_list, chunk_sz, expected):
    """Test chunk_list divides lists evenly, handles remainders, and manages invalid chunk sizes."""
    # Arrange & Act
    actual = chunk_list(input_list, chunk_sz)
    # Assert
    assert actual == expected


# ==============================================================================
# String Sanitization Tests
# ==============================================================================

@pytest.mark.parametrize("input_name, expected", [
    ("7ELEVEN", "7eleven"),
    ("Big C Supercenter", "big_c_supercenter"),
    ("HomePro (HQ) #001", "homepro_hq_001"),
    ("", "merchant"),
    ("   ", "merchant"),
    ("!!!@@@", "merchant"),
])
def test_string_sanitization_parameterized(input_name, expected):
    """Test sanitize_short_name standardizes entity names and falls back to default on empty."""
    # Arrange & Act
    actual = sanitize_short_name(input_name)
    # Assert
    assert actual == expected
