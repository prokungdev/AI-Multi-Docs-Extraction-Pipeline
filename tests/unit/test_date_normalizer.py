"""
Unit tests for Date Normalization (Buddhist Era to Christian Era / ISO format).
Pure domain logic validation without I/O or network dependencies.
"""

import pytest
from src.domain.services.post_processor import normalize_date_to_ad


@pytest.mark.parametrize("input_date, expected", [
    ("2567-05-15", "2024-05-15"),
    ("2568/12/31", "2025-12-31"),
    ("15/05/2567", "2024-05-15"),
    ("01-01-2566", "2023-01-01"),
    ("2024-05-15", "2024-05-15"),
    ("15/05/2024", "2024-05-15"),
    ("2500-01-01", "2500-01-01"),
    ("2501-01-01", "1958-01-01"),
    ("", ""),
    (None, ""),
    ("   ", ""),
    ("invalid-date-string", "invalid-date-string"),
])
def test_date_normalization_parameterized(input_date, expected):
    """Test date normalization handles BE/AD, formats, boundaries, and empty strings."""
    # Arrange & Act
    actual = normalize_date_to_ad(input_date)
    # Assert
    assert actual == expected
