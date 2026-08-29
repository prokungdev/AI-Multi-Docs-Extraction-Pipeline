"""
Integration test suite for Accounting & Target System Master Models and Real-World Seed Data.
Verifies Phase 1 deliverables: Master Tables, Enums, Merchants, and Journal Vouchers CRUD.
"""

import os
import gc
import uuid
import unittest
import tempfile
from sqlalchemy import select

from src.infrastructure.database.engine import get_db_session, dispose_all_engines
from src.infrastructure.database.schema import initialize_db_schema
from src.infrastructure.database.seeder import seed_initial_data
from src.infrastructure.database.models import (
    IntegrationMethod,
    TargetSystem,
    VoucherStatus,
    ConsolidateMode,
    ExpenseType,
    ExpenseAccountMapping,
    Merchant,
    ExpenseReceipt,
    Company,
    Batch,
    DocumentControl,
    JournalVoucher,
    JournalVoucherItem,
)
from src.infrastructure.core.constants import (
    VatType,
    TargetSystemId,
    ConsolidateModeCode,
    VoucherStatusCode,
    EntityIdPrefix,
    generate_entity_id,
    SystemUserId,
    DefaultCompany,
)


class TestAccountingMasterData(unittest.TestCase):
    """
    Test suite for Master Tables and Seed Data in Phase 1.
    """

    @classmethod
    def setUpClass(cls):
        cls._orig_db_override = os.environ.get("DB_PATH_OVERRIDE")
        cls.db_path = os.path.join(tempfile.gettempdir(), f"test_acct_master_{uuid.uuid4().hex[:8]}.db").replace("\\", "/")
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path
        initialize_db_schema()
        seed_initial_data()

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

    def test_01_integration_methods_seeded(self):
        """Verify integration_methods master table seeding."""
        with get_db_session() as session:
            methods = session.scalars(select(IntegrationMethod)).all()
            method_ids = [m.method_id for m in methods]
            self.assertIn("RPA_UIPATH", method_ids)
            self.assertIn("REST_API", method_ids)
            self.assertIn("CSV_EXPORT", method_ids)

    def test_02_target_systems_seeded(self):
        """Verify target_systems master table seeding and relationship."""
        with get_db_session() as session:
            systems = session.scalars(select(TargetSystem)).all()
            system_ids = [s.system_id for s in systems]
            self.assertIn(TargetSystemId.EXPRESS.value, system_ids)
            self.assertIn(TargetSystemId.SAP.value, system_ids)
            self.assertIn(TargetSystemId.PEAK.value, system_ids)

            express = session.scalars(select(TargetSystem).filter_by(system_id="EXPRESS")).first()
            self.assertEqual(express.integration_method_id, "RPA_UIPATH")

    def test_03_voucher_statuses_seeded(self):
        """Verify voucher_statuses master table lifecycle statuses."""
        with get_db_session() as session:
            statuses = session.scalars(select(VoucherStatus)).all()
            status_codes = [s.status_code for s in statuses]
            for expected in ["DRAFT", "READY", "POSING", "POSTED", "ERROR", "CANCELLED"]:
                self.assertIn(expected, status_codes)

    def test_04_consolidate_modes_seeded(self):
        """Verify consolidate_modes table and default BY_MERCHANT flag."""
        with get_db_session() as session:
            modes = session.scalars(select(ConsolidateMode)).all()
            mode_codes = [m.mode_code for m in modes]
            self.assertIn(ConsolidateModeCode.BY_MERCHANT.value, mode_codes)
            self.assertIn(ConsolidateModeCode.BY_CATEGORY.value, mode_codes)

            by_merchant = session.scalars(select(ConsolidateMode).filter_by(mode_code="BY_MERCHANT")).first()
            self.assertEqual(by_merchant.is_default, 1)

    def test_05_expense_types_seeded(self):
        """Verify expense_types master table with WHT default rates."""
        with get_db_session() as session:
            service_type = session.scalars(select(ExpenseType).filter_by(expense_type_name="ค่าบริการ")).first()
            self.assertIsNotNone(service_type)
            self.assertEqual(service_type.default_wht_rate, 3.0)

            transport_type = session.scalars(select(ExpenseType).filter_by(expense_type_name="ค่าขนส่ง")).first()
            self.assertIsNotNone(transport_type)
            self.assertEqual(transport_type.default_wht_rate, 1.0)

    def test_06_expense_account_mappings_seeded(self):
        """Verify expense_account_mappings seeded with Express account codes."""
        with get_db_session() as session:
            mappings = session.scalars(select(ExpenseAccountMapping)).all()
            self.assertGreaterEqual(len(mappings), 2)
            mapping_dict = {m.expense_type_name: m.account_code for m in mappings}
            self.assertEqual(mapping_dict.get("ค่าบริการ"), "95-5310-19")
            self.assertEqual(mapping_dict.get("ค่าขนส่ง"), "95-5200-05")

    def test_07_real_world_merchants_seeded(self):
        """Verify Grab, SPX, Shopee real-world test merchants seeding."""
        with get_db_session() as session:
            grab = session.scalars(select(Merchant).filter_by(vendor_code="G0001")).first()
            self.assertIsNotNone(grab)
            self.assertEqual(grab.default_expense_type, "ค่าบริการ")
            self.assertEqual(grab.default_vat_type, VatType.EXCLUSIVE.value)
            self.assertEqual(grab.has_wht, 1)
            self.assertEqual(grab.default_wht_rate, 3.0)

            spx = session.scalars(select(Merchant).filter_by(vendor_code="อ0022")).first()
            self.assertIsNotNone(spx)
            self.assertEqual(spx.default_expense_type, "ค่าขนส่ง")
            self.assertEqual(spx.default_vat_type, VatType.NO_VAT.value)
            self.assertEqual(spx.has_wht, 0)

            shopee = session.scalars(select(Merchant).filter_by(vendor_code="S0002")).first()
            self.assertIsNotNone(shopee)
            self.assertEqual(shopee.default_expense_type, "ค่าบริการ")
            self.assertEqual(shopee.default_vat_type, VatType.INCLUSIVE.value)

    def test_08_journal_voucher_and_item_crud(self):
        """Verify pure SQLAlchemy 2.0 ORM CRUD for JournalVoucher and JournalVoucherItem."""
        with get_db_session() as session:
            company = session.scalars(select(Company).filter_by(company_code=DefaultCompany.CODE)).first()
            batch_id = generate_entity_id(EntityIdPrefix.BATCH)
            session.add(Batch(
                batch_id=batch_id,
                company_id=company.company_id,
                original_filename="sample_batch.pdf",
                total_pages=1,
                storage_path="storage/sample.pdf",
                file_hash=uuid.uuid4().hex,
                created_by=SystemUserId.SYSTEM_ADMIN
            ))
            doc_id = generate_entity_id(EntityIdPrefix.DOCUMENT)
            session.add(DocumentControl(
                document_id=doc_id,
                company_id=company.company_id,
                batch_id=batch_id,
                doc_type_id="expense_receipt",
                status_code="APPROVED",
                created_by=SystemUserId.SYSTEM_ADMIN
            ))
            session.flush()

            vch_id = generate_entity_id(EntityIdPrefix.VOUCHER)
            voucher = JournalVoucher(
                voucher_id=vch_id,
                document_id=doc_id,
                company_id=company.company_id,
                batch_id=batch_id,
                target_system_id="EXPRESS",
                voucher_type="OE",
                voucher_no="OE260730002",
                voucher_date="2026-07-30",
                vendor_code="G0001",
                vendor_name="Grabtaxi (Thailand) Co., Ltd.",
                vendor_tax_id="0105556090377",
                subtotal_amount=1939.50,
                vat_type=VatType.EXCLUSIVE.value,
                vat_rate=7.0,
                vat_amount=135.77,
                wht_amount=58.19,
                net_amount=2075.27,
                status_code=VoucherStatusCode.READY.value,
                created_by=SystemUserId.SYSTEM_ADMIN
            )
            session.add(voucher)
            session.flush()

            item_id = generate_entity_id(EntityIdPrefix.VOUCHER_ITEM)
            item = JournalVoucherItem(
                item_id=item_id,
                voucher_id=vch_id,
                line_number=1,
                entry_type="DEBIT",
                account_code="95-5310-19",
                account_name="ค่าบริการและที่ปรึกษา",
                amount=1939.50,
                created_by=SystemUserId.SYSTEM_ADMIN
            )
            session.add(item)
            session.flush()

            # Query back with relationship
            queried_vch = session.scalars(select(JournalVoucher).filter_by(voucher_id=vch_id)).first()
            self.assertIsNotNone(queried_vch)
            self.assertEqual(queried_vch.voucher_no, "OE260730002")
            self.assertEqual(len(queried_vch.items), 1)
            self.assertEqual(queried_vch.items[0].account_code, "95-5310-19")
