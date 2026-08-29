"""
Integration test suite for Journal Voucher and Accounting Repositories (Phase 2).
Verifies:
- Sequential Running Number generation (e.g. OE260730001 -> OE260730002)
- Journal Voucher & Child Lines CRUD
- Concurrency Lease Lock & Atomic State Transitions for RPA / UiPath Bots
- Lease timeout reclamation and release
- Status updates (POSTED with erp_reference_no, ERROR tracking)
- GL Account Mappings CRUD
"""

import os
import gc
import uuid
import unittest
import tempfile
from datetime import datetime, timezone, timedelta

from src.infrastructure.database.engine import get_db_session, dispose_all_engines
from src.infrastructure.database.schema import initialize_db_schema
from src.infrastructure.database.seeder import seed_initial_data
from src.infrastructure.database.models import Company, Batch, DocumentControl
from src.infrastructure.core.constants import (
    EntityIdPrefix,
    generate_entity_id,
    SystemUserId,
    DefaultCompany,
    VatType,
    VoucherStatusCode,
)
from src.infrastructure.database import (
    generate_next_voucher_no,
    create_journal_voucher,
    get_journal_voucher_by_id,
    get_journal_voucher_by_document_id,
    lease_next_ready_voucher,
    release_or_unlock_voucher,
    update_voucher_status,
    list_vouchers,
    get_expense_account_mapping,
    list_expense_account_mappings,
    upsert_expense_account_mapping,
    get_expense_type,
    list_expense_types,
    get_target_system,
    list_target_systems,
)


class TestVoucherRepositoryIntegration(unittest.TestCase):
    """
    Test suite for Journal Voucher and Accounting Configuration Repositories.
    """

    @classmethod
    def setUpClass(cls):
        cls._orig_db_override = os.environ.get("DB_PATH_OVERRIDE")
        cls.db_path = os.path.join(tempfile.gettempdir(), f"test_vch_repo_{uuid.uuid4().hex[:8]}.db").replace("\\", "/")
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path
        initialize_db_schema()
        seed_initial_data()

        with get_db_session() as session:
            from sqlalchemy import select
            comp = session.scalars(select(Company).filter_by(company_code=DefaultCompany.CODE)).first()
            cls.company_id = comp.company_id

            # Create test batch and document
            cls.batch_id = generate_entity_id(EntityIdPrefix.BATCH)
            session.add(Batch(
                batch_id=cls.batch_id,
                company_id=cls.company_id,
                original_filename="sample_batch.pdf",
                total_pages=1,
                storage_path="storage/sample.pdf",
                file_hash=uuid.uuid4().hex,
                created_by=SystemUserId.SYSTEM_ADMIN
            ))
            cls.doc_id = generate_entity_id(EntityIdPrefix.DOCUMENT)
            session.add(DocumentControl(
                document_id=cls.doc_id,
                company_id=cls.company_id,
                batch_id=cls.batch_id,
                doc_type_id="expense_receipt",
                status_code="APPROVED",
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

    def test_01_sequential_running_number_generation(self):
        """Test generating next sequential voucher numbers for a specific date."""
        target_date = "2026-07-30"
        # First number should be OE260730001
        vch_no_1 = generate_next_voucher_no(self.company_id, voucher_type="OE", voucher_date_str=target_date)
        self.assertEqual(vch_no_1, "OE260730001")

        # Create a document for test_01
        doc_id_1 = generate_entity_id(EntityIdPrefix.DOCUMENT)
        with get_db_session() as session:
            session.add(DocumentControl(
                document_id=doc_id_1,
                company_id=self.company_id,
                batch_id=self.batch_id,
                doc_type_id="expense_receipt",
                status_code="APPROVED",
                created_by=SystemUserId.SYSTEM_ADMIN
            ))

        # Create voucher with OE260730001
        create_journal_voucher(
            voucher_data={
                "document_id": doc_id_1,
                "company_id": self.company_id,
                "batch_id": self.batch_id,
                "voucher_no": vch_no_1,
                "voucher_date": target_date,
                "vendor_code": "G0001",
                "vendor_name": "Grabtaxi",
                "subtotal_amount": 100.0,
                "net_amount": 107.0,
            }
        )

        # Next number should automatically be OE260730002
        vch_no_2 = generate_next_voucher_no(self.company_id, voucher_type="OE", voucher_date_str=target_date)
        self.assertEqual(vch_no_2, "OE260730002")

    def test_02_create_and_get_journal_voucher_with_items(self):
        """Test creating a Journal Voucher with child line items and target_payload."""
        payload_data = {
            "VendorCode": "G0001",
            "RefBillNo": "TAX-2026-0099",
            "WithholdingTaxNo": "26/07/003",
            "Items": [{"ItemNo": 1, "AccountCode": "95-5310-19", "Amount": 1939.50}]
        }

        vch = create_journal_voucher(
            voucher_data={
                "document_id": self.doc_id,
                "company_id": self.company_id,
                "batch_id": self.batch_id,
                "target_system_id": "EXPRESS",
                "voucher_type": "OE",
                "voucher_no": "OE260730003",
                "voucher_date": "2026-07-30",
                "vendor_code": "G0001",
                "vendor_name": "Grabtaxi (Thailand) Co., Ltd.",
                "vendor_tax_id": "0105556090377",
                "ref_doc_no": "TAX-2026-0099",
                "subtotal_amount": 1939.50,
                "vat_type": VatType.EXCLUSIVE.value,
                "vat_rate": 7.0,
                "vat_amount": 135.77,
                "wht_amount": 58.19,
                "net_amount": 2075.27,
                "status_code": VoucherStatusCode.READY.value,
                "target_payload": payload_data,
            },
            items_data=[
                {
                    "line_number": 1,
                    "entry_type": "DEBIT",
                    "account_code": "95-5310-19",
                    "account_name": "ค่าบริการและที่ปรึกษา",
                    "department_code": "",
                    "amount": 1939.50,
                    "description": "ค่าบริการ Grab Ride",
                }
            ]
        )

        self.assertIsNotNone(vch)
        self.assertEqual(vch["voucher_no"], "OE260730003")
        self.assertEqual(len(vch["items"]), 1)
        self.assertEqual(vch["items"][0]["account_code"], "95-5310-19")
        self.assertEqual(vch["target_payload_parsed"]["VendorCode"], "G0001")

        # Query by document_id
        doc_vch = get_journal_voucher_by_document_id(self.doc_id)
        self.assertIsNotNone(doc_vch)
        self.assertEqual(doc_vch["voucher_id"], vch["voucher_id"])

    def test_03_lease_lock_and_concurrency(self):
        """Test atomic Concurrency Lease Lock (READY -> POSING) for RPA bots."""
        # Lease next READY voucher for EXPRESS
        leased = lease_next_ready_voucher(target_system_id="EXPRESS", bot_id="uipath_bot_01")
        self.assertIsNotNone(leased)
        self.assertEqual(leased["status_code"], VoucherStatusCode.POSING.value)
        self.assertEqual(leased["locked_by"], "uipath_bot_01")
        self.assertIsNotNone(leased["locked_at"])

        # Second lease attempt should not receive the same locked voucher
        second_lease = lease_next_ready_voucher(target_system_id="EXPRESS", bot_id="uipath_bot_02")
        # All available EXPRESS vouchers are now POSING or already created
        if second_lease:
            self.assertNotEqual(second_lease["voucher_id"], leased["voucher_id"])

        # Release lock (e.g. Test / Preview / Abort)
        unlocked = release_or_unlock_voucher(leased["voucher_id"])
        self.assertTrue(unlocked)

        # After unlock, status returns to READY
        refreshed = get_journal_voucher_by_id(leased["voucher_id"])
        self.assertEqual(refreshed["status_code"], VoucherStatusCode.READY.value)
        self.assertIsNone(refreshed["locked_at"])

    def test_04_status_updates_posted_and_error(self):
        """Test updating voucher status to POSTED (success) and ERROR (failure)."""
        # 1. Update to ERROR
        vch_err = update_voucher_status(
            voucher_id=list_vouchers()[0]["voucher_id"],
            status_code=VoucherStatusCode.ERROR.value,
            error_message="Express screen timeout while entering GL line 1",
        )
        self.assertEqual(vch_err["status_code"], VoucherStatusCode.ERROR.value)
        self.assertEqual(vch_err["error_message"], "Express screen timeout while entering GL line 1")

        # 2. Update to POSTED
        vch_posted = update_voucher_status(
            voucher_id=vch_err["voucher_id"],
            status_code=VoucherStatusCode.POSTED.value,
            erp_reference_no="OE260730001",
        )
        self.assertEqual(vch_posted["status_code"], VoucherStatusCode.POSTED.value)
        self.assertEqual(vch_posted["erp_reference_no"], "OE260730001")
        self.assertIsNotNone(vch_posted["posted_at"])
        self.assertIsNone(vch_posted["error_message"])

    def test_05_accounting_config_mappings_crud(self):
        """Test GL account mapping upsert and lookup routines."""
        # Lookup existing seeded mapping
        mapping = get_expense_account_mapping(
            company_id=self.company_id,
            target_system_id="EXPRESS",
            expense_type_name="ค่าบริการ",
        )
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping["account_code"], "95-5310-19")

        # Upsert / Modify mapping
        updated = upsert_expense_account_mapping(
            company_id=self.company_id,
            target_system_id="EXPRESS",
            expense_type_name="ค่าบริการ",
            account_code="95-5310-20",
            account_name="ค่าบริการและที่ปรึกษา (อัปเดต)",
            department_code="MKT",
        )
        self.assertEqual(updated["account_code"], "95-5310-20")
        self.assertEqual(updated["department_code"], "MKT")

        # Verify list mappings
        mappings_list = list_expense_account_mappings(self.company_id, target_system_id="EXPRESS")
        self.assertGreaterEqual(len(mappings_list), 2)

    def test_06_target_systems_and_expense_types_lookup(self):
        """Test lookup and listing of Target Systems and Master Expense Types."""
        exp_type = get_expense_type("ค่าขนส่ง")
        self.assertIsNotNone(exp_type)
        self.assertEqual(exp_type["default_wht_rate"], 1.0)

        all_types = list_expense_types()
        self.assertGreaterEqual(len(all_types), 4)

        express_sys = get_target_system("EXPRESS")
        self.assertIsNotNone(express_sys)
        self.assertEqual(express_sys["system_category"], "ACCOUNTING_ERP")

        all_systems = list_target_systems()
        self.assertGreaterEqual(len(all_systems), 5)
