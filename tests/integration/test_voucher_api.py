"""
Integration test suite for UiPath RPA Gateway REST API (/api/v1/vouchers/get-next).
Verifies:
- GET /api/v1/vouchers/get-next (Preview mode without lease lock)
- POST /api/v1/vouchers/get-next (Atomic lease lock transitions READY -> POSING)
- POST /api/v1/vouchers/{voucher_id}/complete (Transitions POSING -> POSTED)
- POST /api/v1/vouchers/{voucher_id}/fail (Transitions POSING -> ERROR)
- POST /api/v1/vouchers/{voucher_id}/unlock (Transitions POSING -> READY)
- Empty queue response when no vouchers are pending
- 100% Lowercase JSON payload format validation
"""

import os
import gc
import uuid
import unittest
import tempfile
from fastapi.testclient import TestClient

from apps.api.main import app
from src.infrastructure.database.engine import get_db_session, dispose_all_engines
from src.infrastructure.database.schema import initialize_db_schema
from src.infrastructure.database.seeder import seed_initial_data
from src.infrastructure.database.models import (
    Company,
    Batch,
    DocumentControl,
)
from src.infrastructure.core.constants import (
    EntityIdPrefix,
    generate_entity_id,
    SystemUserId,
    DefaultCompany,
    VoucherStatusCode,
)
from src.infrastructure.database import (
    insert_relational_receipt,
    get_journal_voucher_by_id,
)
from src.application.usecases.voucher_generator import generate_voucher_for_document


class TestVoucherApiIntegration(unittest.TestCase):
    """
    Integration test suite for RPA Gateway REST API using FastAPI TestClient.
    """

    @classmethod
    def setUpClass(cls):
        cls._orig_db_override = os.environ.get("DB_PATH_OVERRIDE")
        cls.db_path = os.path.join(tempfile.gettempdir(), f"test_vch_api_{uuid.uuid4().hex[:8]}.db").replace("\\", "/")
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path
        initialize_db_schema()
        seed_initial_data()

        cls.client = TestClient(app)

        with get_db_session() as session:
            from sqlalchemy import select
            comp = session.scalars(select(Company).filter_by(company_code=DefaultCompany.CODE)).first()
            cls.company_id = comp.company_id

            # Create test batch
            cls.batch_id = generate_entity_id(EntityIdPrefix.BATCH)
            session.add(Batch(
                batch_id=cls.batch_id,
                company_id=cls.company_id,
                original_filename="api_test_batch.pdf",
                total_pages=2,
                storage_path="storage/api_test_batch.pdf",
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

    def _seed_document_and_voucher(self, receipt_data: dict, ref_no: str) -> str:
        """Helper to create a document, receipt, and ready voucher."""
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
            payload=receipt_data,
            original_filename=f"{ref_no}.pdf",
            created_by=SystemUserId.SYSTEM_ADMIN,
            company_id=self.company_id,
        )

        vch = generate_voucher_for_document(doc_id)
        return vch["voucher_id"]

    def test_01_empty_queue_returns_null_data(self):
        """Test calling get-next on an empty queue returns status: success and data: null."""
        response = self.client.post("/api/v1/vouchers/get-next", json={"target_system_id": "EXPRESS"})
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data["status"], "success")
        self.assertIsNone(json_data["data"])
        self.assertIn("No pending vouchers", json_data["message"])

    def test_02_get_preview_mode_does_not_lock(self):
        """Test GET /api/v1/vouchers/get-next previews the voucher without locking."""
        grab_payload = {
            "merchant": {"name": "Grabtaxi (Thailand) Co., Ltd.", "tax_id": "0105556090377"},
            "receipt_info": {"receipt_number": "GRAB-001", "transaction_date": "2026-07-30"},
            "totals": {"subtotal": 500.00, "vat_amount": 35.00, "wht_amount": 15.00, "wht_rate": 3.0, "net_amount": 535.00},
            "items": [{"name": "Ride Service", "quantity": 1, "unit_price": 500.00, "total_price": 500.00}]
        }
        vch_id = self._seed_document_and_voucher(grab_payload, "GRAB_PREVIEW")

        # Call GET get-next (defaults to preview=True)
        response = self.client.get("/api/v1/vouchers/get-next?target_system_id=EXPRESS")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertIsNotNone(body["data"])
        self.assertEqual(body["data"]["voucher_id"], vch_id)
        self.assertEqual(body["data"]["vendor_code"], "G0001")
        self.assertEqual(body["data"]["subtotal"], 500.00)
        self.assertEqual(body["data"]["wht_no"], "26/07/001")

        # Verify DB status is STILL READY (not locked)
        db_vch = get_journal_voucher_by_id(vch_id)
        self.assertEqual(db_vch["status_code"], VoucherStatusCode.READY.value)
        self.assertIsNone(db_vch["locked_at"])

    def test_03_post_lease_locks_and_delivers_payload(self):
        """Test POST /api/v1/vouchers/get-next atomically leases and transitions to POSING."""
        response = self.client.post(
            "/api/v1/vouchers/get-next",
            json={"bot_id": "uipath_worker_101", "target_system_id": "EXPRESS", "preview": False}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        data = body["data"]
        self.assertIsNotNone(data)
        vch_id = data["voucher_id"]

        # Validate lowercase JSON payload structure
        self.assertEqual(data["vendor_code"], "G0001")
        self.assertEqual(data["voucher_date"], "30/07/69")
        self.assertEqual(data["vat_type_id"], 2)
        self.assertEqual(data["wht_no"], "26/07/001")
        self.assertEqual(len(data["lines"]), 1)
        self.assertEqual(data["lines"][0]["account_code"], "95-5310-19")

        # Verify DB status is now POSING
        db_vch = get_journal_voucher_by_id(vch_id)
        self.assertEqual(db_vch["status_code"], VoucherStatusCode.POSING.value)
        self.assertIsNotNone(db_vch["locked_at"])
        self.assertEqual(db_vch["locked_by"], "uipath_worker_101")

    def test_04_unlock_voucher_returns_to_ready(self):
        """Test POST /api/v1/vouchers/{voucher_id}/unlock returns voucher to READY."""
        # Find the leased voucher
        with get_db_session() as session:
            from sqlalchemy import select
            from src.infrastructure.database.models import JournalVoucher
            vch = session.scalars(select(JournalVoucher).filter_by(status_code=VoucherStatusCode.POSING.value)).first()
            vch_id = vch.voucher_id

        res = self.client.post(f"/api/v1/vouchers/{vch_id}/unlock")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "success")

        # Check DB status
        refreshed = get_journal_voucher_by_id(vch_id)
        self.assertEqual(refreshed["status_code"], VoucherStatusCode.READY.value)
        self.assertIsNone(refreshed["locked_at"])

    def test_05_complete_voucher_transitions_to_posted(self):
        """Test POST /api/v1/vouchers/{voucher_id}/complete marks voucher as POSTED."""
        # Re-lease
        lease_res = self.client.post("/api/v1/vouchers/get-next", json={"bot_id": "uipath_worker_101"})
        vch_id = lease_res.json()["data"]["voucher_id"]

        # Call complete
        comp_res = self.client.post(
            f"/api/v1/vouchers/{vch_id}/complete",
            json={"erp_reference_no": "OE260730001"}
        )
        self.assertEqual(comp_res.status_code, 200)
        body = comp_res.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["erp_reference_no"], "OE260730001")

        # Check DB
        db_vch = get_journal_voucher_by_id(vch_id)
        self.assertEqual(db_vch["status_code"], VoucherStatusCode.POSTED.value)
        self.assertEqual(db_vch["erp_reference_no"], "OE260730001")
        self.assertIsNotNone(db_vch["posted_at"])

    def test_06_fail_voucher_transitions_to_error(self):
        """Test POST /api/v1/vouchers/{voucher_id}/fail records error reason."""
        spx_payload = {
            "merchant": {"name": "SPX Express (Thailand) Co., Ltd.", "tax_id": "0105562002073"},
            "receipt_info": {"receipt_number": "SPX-ERR-001", "transaction_date": "2026-07-30"},
            "totals": {"subtotal": 120.00, "vat_amount": 0.0, "net_amount": 120.00},
            "items": [{"name": "Parcel", "quantity": 1, "unit_price": 120.00, "total_price": 120.00}]
        }
        vch_id = self._seed_document_and_voucher(spx_payload, "SPX_ERR")

        # Lease it
        lease_res = self.client.post("/api/v1/vouchers/get-next")
        leased_id = lease_res.json()["data"]["voucher_id"]
        self.assertEqual(leased_id, vch_id)

        # Call fail
        fail_res = self.client.post(
            f"/api/v1/vouchers/{vch_id}/fail",
            json={"error_message": "Express screen lock detected on line 1"}
        )
        self.assertEqual(fail_res.status_code, 200)
        self.assertEqual(fail_res.json()["status"], "success")

        # Check DB
        db_vch = get_journal_voucher_by_id(vch_id)
        self.assertEqual(db_vch["status_code"], VoucherStatusCode.ERROR.value)
        self.assertEqual(db_vch["error_message"], "Express screen lock detected on line 1")
