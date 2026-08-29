"""
End-to-End Integration test suite for Voucher Generation Pipeline (Phase 4).
Verifies:
- Generating Express OE Voucher for Grabtaxi (Thailand) (Vendor G0001, VatType 2, WHT 3%)
- Generating Express OE Voucher for SPX Express (Vendor อ0022, VatType 0, No WHT)
- Generating Express OE Voucher for Shopee (Vendor S0002, VatType 1, No WHT)
- Automated Batch Voucher Generation
- Idempotency & duplicate voucher prevention
"""

import os
import gc
import uuid
import unittest
import tempfile

from src.infrastructure.database.engine import get_db_session, dispose_all_engines
from src.infrastructure.database.schema import initialize_db_schema
from src.infrastructure.database.seeder import seed_initial_data
from src.infrastructure.database.models import (
    Company,
    Batch,
    DocumentControl,
    Merchant,
)
from src.infrastructure.core.constants import (
    EntityIdPrefix,
    generate_entity_id,
    SystemUserId,
    DefaultCompany,
    VatType,
    VoucherStatusCode,
)
from src.infrastructure.database import (
    insert_relational_receipt,
    get_journal_voucher_by_id,
    get_journal_voucher_by_document_id,
    list_vouchers,
)
from src.application.usecases.voucher_generator import (
    generate_voucher_for_document,
    generate_vouchers_for_batch,
)


class TestVoucherGenerationIntegration(unittest.TestCase):
    """
    End-to-end integration test suite for Journal Voucher and Express Output generation.
    """

    @classmethod
    def setUpClass(cls):
        cls._orig_db_override = os.environ.get("DB_PATH_OVERRIDE")
        cls.db_path = os.path.join(tempfile.gettempdir(), f"test_vch_e2e_{uuid.uuid4().hex[:8]}.db").replace("\\", "/")
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path
        initialize_db_schema()
        seed_initial_data()

        with get_db_session() as session:
            from sqlalchemy import select
            comp = session.scalars(select(Company).filter_by(company_code=DefaultCompany.CODE)).first()
            cls.company_id = comp.company_id

            # Create test batch
            cls.batch_id = generate_entity_id(EntityIdPrefix.BATCH)
            session.add(Batch(
                batch_id=cls.batch_id,
                company_id=cls.company_id,
                original_filename="e2e_vouchers_batch.pdf",
                total_pages=3,
                storage_path="storage/sample_batch.pdf",
                file_hash=uuid.uuid4().hex,
                created_by=SystemUserId.SYSTEM_ADMIN
            ))

    @classmethod
    def tearDownClass(cls):
        dispose_all_engines()
        gc.collect()
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
        if cls._orig_db_override:
            os.environ["DB_PATH_OVERRIDE"] = cls._orig_db_override
        else:
            os.environ.pop("DB_PATH_OVERRIDE", None)

    def _create_document_and_receipt(self, payload: dict, doc_number: str, date_str: str) -> str:
        """Helper to create a DocumentControl and insert an ExpenseReceipt."""
        doc_id = generate_entity_id(EntityIdPrefix.DOCUMENT)
        with get_db_session() as session:
            session.add(DocumentControl(
                document_id=doc_id,
                company_id=self.company_id,
                batch_id=self.batch_id,
                doc_type_id="expense_receipt",
                status_code="APPROVED",
                created_by=SystemUserId.SYSTEM_ADMIN
            ))
        
        insert_relational_receipt(
            document_id=doc_id,
            payload=payload,
            original_filename=f"{doc_number}.pdf",
            created_by=SystemUserId.SYSTEM_ADMIN,
            company_id=self.company_id,
        )
        return doc_id

    def test_01_grabtaxi_voucher_generation(self):
        """
        Test generating voucher for Grabtaxi (Thailand):
        - Tax ID: 0105556090377 -> VendorCode: G0001
        - Subtotal: 1,939.50, VAT: 135.77 (EXCLUSIVE -> VatTypeId: 2), WHT: 3% (58.19)
        - Expected VoucherNo: OE260730001, WithholdingTaxNo: 26/07/001
        - Expected AccountCode: 95-5310-19
        """
        grab_payload = {
            "merchant": {
                "name": "Grabtaxi (Thailand) Co., Ltd.",
                "tax_id": "0105556090377",
                "branch_code": "00000",
            },
            "receipt_info": {
                "receipt_number": "GRAB-TAX-INV-2026-00008899",
                "transaction_date": "2026-07-30",
            },
            "totals": {
                "subtotal": 1939.50,
                "vat_amount": 135.77,
                "wht_amount": 58.19,
                "wht_rate": 3.0,
                "net_amount": 2075.27,
            },
            "items": [
                {"name": "Grab Transport Services", "quantity": 1, "unit_price": 1939.50, "total_price": 1939.50}
            ]
        }

        doc_id = self._create_document_and_receipt(grab_payload, "GRAB_01", "2026-07-30")
        vch = generate_voucher_for_document(doc_id)

        self.assertIsNotNone(vch)
        self.assertEqual(vch["voucher_no"], "OE260730001")
        self.assertEqual(vch["status_code"], VoucherStatusCode.READY.value)
        self.assertEqual(vch["vendor_code"], "G0001")
        self.assertEqual(vch["subtotal_amount"], 1939.50)
        self.assertEqual(vch["vat_amount"], 135.77)
        self.assertEqual(vch["wht_amount"], 58.19)
        self.assertEqual(vch["net_amount"], 2075.27)

        # Check Express OE JSON Payload
        payload = vch["target_payload_parsed"]
        self.assertIsNotNone(payload)
        self.assertEqual(payload["voucher_no"], "OE260730001")
        self.assertEqual(payload["voucher_date"], "30/07/69")
        self.assertEqual(payload["vendor_code"], "G0001")
        self.assertEqual(payload["vat_type_id"], 2)
        self.assertEqual(payload["vat_amount"], 135.77)
        self.assertEqual(payload["wht_no"], "26/07/001")
        self.assertEqual(payload["wht_rate"], 3.0)
        self.assertEqual(payload["wht_amount"], 58.19)
        self.assertEqual(len(payload["ref_bill_no"]), 14)
        self.assertEqual(payload["lines"][0]["account_code"], "95-5310-19")

    def test_02_spx_express_voucher_generation(self):
        """
        Test generating voucher for SPX Express:
        - Tax ID: 0105562002073 -> VendorCode: อ0022
        - Subtotal: 450.00, VAT: 0.0 (NO_VAT -> VatTypeId: 0), No WHT
        - Expected VoucherNo: OE260730002, WithholdingTaxNo: None
        - Expected AccountCode: 95-5200-05 (ค่าขนส่ง)
        """
        spx_payload = {
            "merchant": {
                "name": "SPX Express (Thailand) Co., Ltd.",
                "tax_id": "0105562002073",
                "branch_code": "00000",
            },
            "receipt_info": {
                "receipt_number": "SPX-INV-998877",
                "transaction_date": "2026-07-30",
            },
            "totals": {
                "subtotal": 450.00,
                "vat_amount": 0.0,
                "net_amount": 450.00,
            },
            "items": [
                {"name": "Standard Delivery", "quantity": 1, "unit_price": 450.00, "total_price": 450.00}
            ]
        }

        doc_id = self._create_document_and_receipt(spx_payload, "SPX_01", "2026-07-30")
        vch = generate_voucher_for_document(doc_id)

        self.assertIsNotNone(vch)
        self.assertEqual(vch["voucher_no"], "OE260730002")
        self.assertEqual(vch["vendor_code"], "อ0022")

        payload = vch["target_payload_parsed"]
        self.assertEqual(payload["vendor_code"], "อ0022")
        self.assertEqual(payload["vat_type_id"], 0)
        self.assertEqual(payload["vat_amount"], 0.0)
        self.assertIsNone(payload["wht_no"])
        self.assertEqual(payload["wht_amount"], 0.0)
        self.assertEqual(payload["lines"][0]["account_code"], "95-5200-05")

    def test_03_shopee_voucher_generation(self):
        """
        Test generating voucher for Shopee (Thailand):
        - Tax ID: 0105558021119 -> VendorCode: S0002
        - Total: 1,000.00, VAT: 65.42 (INCLUSIVE -> VatTypeId: 1), No WHT
        - Expected VoucherNo: OE260730003, WithholdingTaxNo: None
        - Expected AccountCode: 95-5310-19
        """
        shopee_payload = {
            "merchant": {
                "name": "Shopee (Thailand) Co., Ltd.",
                "tax_id": "0105558021119",
                "branch_code": "00000",
            },
            "receipt_info": {
                "receipt_number": "SHOPEE-INV-2026-001",
                "transaction_date": "2026-07-30",
            },
            "totals": {
                "subtotal": 934.58,
                "vat_amount": 65.42,
                "net_amount": 1000.00,
            },
            "items": [
                {"name": "E-Commerce Service Fee", "quantity": 1, "unit_price": 1000.00, "total_price": 1000.00}
            ]
        }

        doc_id = self._create_document_and_receipt(shopee_payload, "SHOPEE_01", "2026-07-30")
        vch = generate_voucher_for_document(doc_id)

        self.assertIsNotNone(vch)
        self.assertEqual(vch["voucher_no"], "OE260730003")
        self.assertEqual(vch["vendor_code"], "S0002")

        payload = vch["target_payload_parsed"]
        self.assertEqual(payload["vendor_code"], "S0002")
        self.assertEqual(payload["vat_type_id"], 1)
        self.assertIsNone(payload["wht_no"])
        self.assertEqual(payload["lines"][0]["account_code"], "95-5310-19")

    def test_04_idempotency_and_batch_generation(self):
        """Test batch voucher generation and idempotency without duplicates."""
        # Call generate_vouchers_for_batch on the batch
        vouchers = generate_vouchers_for_batch(self.batch_id)
        # All 3 documents in this batch already have vouchers generated
        self.assertEqual(len(vouchers), 3)

        # Total vouchers in DB should still be exactly 3
        all_vchs = list_vouchers(company_id=self.company_id)
        self.assertEqual(len(all_vchs), 3)
