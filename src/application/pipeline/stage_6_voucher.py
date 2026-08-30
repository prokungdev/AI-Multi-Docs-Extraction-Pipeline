"""
Stage 6: Journal Voucher Generation Pipeline Stage.

Coordinates canonical Journal Voucher creation, GL account mapping, sequential running numbers,
and 50-Tawi withholding tax calculation.
Delegates core voucher generation logic to VoucherGeneratorUseCase.
"""

from typing import Dict, Any, Optional
from src.application.usecases.voucher_generator import (
    generate_voucher_for_document,
    generate_vouchers_for_batch,
)


def generate_journal_vouchers(
    batch_id: str,
    company_code: Optional[str] = None,
    force_regenerate: bool = False,
) -> Dict[str, Any]:
    """
    Stage 6: Journal Voucher Generation Entry Point.
    Generates Journal Vouchers for all confirmed documents in target batch.
    """
    return generate_vouchers_for_batch(
        batch_id=batch_id,
        company_code=company_code,
        force_regenerate=force_regenerate,
    )


__all__ = [
    "generate_voucher_for_document",
    "generate_vouchers_for_batch",
    "generate_journal_vouchers",
]
