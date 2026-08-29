"""Integration tests for DocumentType Entity, Seeder, and Quality Thresholds Resolution."""

import os
import unittest
from sqlalchemy import select

from src.infrastructure.core.constants import DocTypeId, ProcessingType, DefaultIdentifier
from src.infrastructure.database import (
    initialize_db_schema,
    seed_initial_data,
    get_db_session,
    DocumentType,
    DocumentControl,
    DocumentStatus,
    Company,
    Batch,
)
from src.application.pipeline.pipeline_helpers import (
    resolve_doc_type_thresholds,
    validate_and_process_payload,
)


class TestDocumentTypesIntegration(unittest.TestCase):
    """Test suite for DocumentType relational model, seeder, and threshold resolution."""

    @classmethod
    def setUpClass(cls):
        initialize_db_schema(drop_and_recreate=True)
        seed_initial_data()

    def test_01_document_types_seeding(self):
        """Verifies that all default document types are correctly seeded with baseline thresholds."""
        with get_db_session() as session:
            doc_types = session.scalars(select(DocumentType)).all()
            self.assertGreaterEqual(len(doc_types), 3)

            dt_map = {dt.doc_type_id: dt for dt in doc_types}
            self.assertIn(DocTypeId.EXPENSE_RECEIPT.value, dt_map)
            self.assertIn(DocTypeId.TAX_INVOICE.value, dt_map)
            self.assertIn(DocTypeId.WITHHOLDING_TAX.value, dt_map)

            # Check expense receipt
            exp = dt_map[DocTypeId.EXPENSE_RECEIPT.value]
            self.assertEqual(exp.processing_type, ProcessingType.AI.value)
            self.assertEqual(exp.confidence_high, 0.85)
            self.assertEqual(exp.confidence_review, 0.70)
            self.assertEqual(exp.confidence_low, 0.60)
            self.assertEqual(exp.financial_tolerance, 0.05)

            # Check tax invoice strict threshold
            tax = dt_map[DocTypeId.TAX_INVOICE.value]
            self.assertEqual(tax.confidence_review, 0.75)

    def test_02_create_archive_only_non_ai_doctype(self):
        """Verifies creating an ARCHIVE_ONLY document type with Nullable AI confidence thresholds."""
        with get_db_session() as session:
            existing = session.scalars(select(DocumentType).filter_by(doc_type_id="citizen_id_card")).first()
            if not existing:
                session.add(DocumentType(
                    doc_type_id="citizen_id_card",
                    display_name="สำเนาบัตรประจำตัวประชาชน",
                    description="เอกสารระบุตัวตนบุคคลธรรมดา (จัดเก็บอย่างเดียว)",
                    processing_type=ProcessingType.ARCHIVE_ONLY.value,
                    sort_order=10,
                    is_active=1,
                    confidence_high=None,
                    confidence_review=None,
                    confidence_low=None,
                    financial_tolerance=None,
                    split_filename_pattern="{doc_type}_{id_number}_{original_filename}_{batch_id}",
                    archive_filename_pattern="{doc_type}_{id_number}_{batch_id}",
                    dpi=150,
                    created_by="usr_admin"
                ))

        with get_db_session() as session:
            card = session.scalars(select(DocumentType).filter_by(doc_type_id="citizen_id_card")).first()
            self.assertIsNotNone(card)
            self.assertEqual(card.processing_type, ProcessingType.ARCHIVE_ONLY.value)
            self.assertIsNone(card.confidence_review)
            self.assertIsNone(card.financial_tolerance)

    def test_03_resolve_doc_type_thresholds_from_db(self):
        """Verifies that resolve_doc_type_thresholds queries database table directly."""
        thresholds = resolve_doc_type_thresholds(DocTypeId.EXPENSE_RECEIPT.value)
        self.assertEqual(thresholds["processing_type"], ProcessingType.AI.value)
        self.assertEqual(thresholds["confidence_review"], 0.70)
        self.assertEqual(thresholds["financial_tolerance"], 0.05)

        card_thresholds = resolve_doc_type_thresholds("citizen_id_card")
        self.assertEqual(card_thresholds["processing_type"], ProcessingType.ARCHIVE_ONLY.value)
        self.assertIsNone(card_thresholds["confidence_review"])

    def test_04_validate_and_process_payload_archive_only(self):
        """Verifies that ARCHIVE_ONLY document types auto-pass validation without AI confidence checks."""
        mock_payload = {
            "financial_summary": {},
            "items": [],
            "extraction_metadata": {"overall_confidence": 0.0, "is_blurry": False},
        }
        processed, status_code, notes = validate_and_process_payload(
            mock_payload,
            doc_type="citizen_id_card"
        )
        self.assertEqual(status_code, "PROCESSED")
        self.assertEqual(len(notes), 0)
        self.assertEqual(processed["extraction_metadata"]["review_priority"], "LOW")
