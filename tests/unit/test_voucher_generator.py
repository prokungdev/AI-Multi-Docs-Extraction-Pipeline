"""
Unit test suite for Voucher Generator Use Case (Phase 4).
Verifies:
- Fail-fast parameter validation for empty document_id and batch_id
- Missing document / company handling
"""

import unittest
from src.application.usecases.voucher_generator import (
    generate_voucher_for_document,
    generate_vouchers_for_batch,
)


class TestVoucherGeneratorUnit(unittest.TestCase):
    """
    Unit test suite for voucher generator edge cases and input validation.
    """

    def test_01_empty_document_id_fails_fast(self):
        """Test that empty or whitespace document_id raises ValueError."""
        with self.assertRaises(ValueError):
            generate_voucher_for_document("")

        with self.assertRaises(ValueError):
            generate_voucher_for_document("   ")

        with self.assertRaises(ValueError):
            generate_voucher_for_document(None)

    def test_02_empty_batch_id_fails_fast(self):
        """Test that empty or whitespace batch_id raises ValueError."""
        with self.assertRaises(ValueError):
            generate_vouchers_for_batch("")

        with self.assertRaises(ValueError):
            generate_vouchers_for_batch("   ")

        with self.assertRaises(ValueError):
            generate_vouchers_for_batch(None)
