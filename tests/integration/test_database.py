import os
import unittest
import uuid
from datetime import datetime, timezone

from src.infrastructure.persistence import (
    initialize_db_schema,
    seed_initial_data,
    create_batch,
    create_page,
    create_document,
    link_pages_to_document,
    check_duplicate_document,
    get_document_by_id,
    get_document_pages,
    get_batch_pages,
    get_pending_documents,
    update_document_to_approved,
    update_document_to_failed,
    update_document_payload,
    search_documents,
    get_doc_types,
    get_sources,
    update_doc_type_active_status,
    update_source_active_status,
)
from sqlalchemy import select
from src.infrastructure.persistence.connection import get_db_session, get_engine, get_database_url
from src.infrastructure.persistence.models import (
    Base,
    ProcessedBatch,
    Document,
    DocumentStatus,
    DocumentPage,
    Merchant,
    MerchantStatus,
    ExpenseReceipt,
    ExpenseReceiptItem,
)
from src.infrastructure.common.constants import DocumentStatusCode


class TestDatabase(unittest.TestCase):
    """
    Test suite for relational SQLite schema initialization, seeding, and CRUD operations.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.db_path = os.path.join(tempfile.gettempdir(), f"test_pipeline_{uuid.uuid4().hex[:8]}.db").replace("\\", "/")
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path

    @classmethod
    def tearDownClass(cls):
        # Clean up the test database file and dispose SQLAlchemy engine
        import gc
        from src.infrastructure.persistence.connection import get_engine
        try:
            get_engine().dispose()
        except Exception:
            pass
        gc.collect()
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
        os.environ.pop("DB_PATH_OVERRIDE", None)

    def test_01_init_and_seed(self):
        """Test database schema initialization and seeding."""
        initialize_db_schema()
        self.assertTrue(os.path.exists(self.db_path))

        seed_initial_data()

        # Verify default doc_types and sources are seeded dynamically
        doc_types = get_doc_types()
        self.assertGreater(len(doc_types), 0)
        dt_id = doc_types[0]["doc_type_id"]

        sources = get_sources(dt_id)
        self.assertGreater(len(sources), 0)
        source_ids = [s["source_id"] for s in sources]
        self.assertIn("NO_TAXID", source_ids)

    def test_02_crud_operations(self):
        """Test batch, page, and document CRUD flows using generic test identifiers."""
        batch_id = "test_batch_123"
        file_hash = "mock_sha256_hash_value"

        # Resolve active doc_type & source dynamically
        doc_types = get_doc_types()
        test_doc_type = doc_types[0]["doc_type_id"] if doc_types else "expense_receipt"
        sources = get_sources(test_doc_type)
        test_source = sources[0]["source_id"] if sources else "NO_TAXID"

        # 1. Create Batch
        success = create_batch(
            batch_id=batch_id,
            original_filename="test_document.pdf",
            total_pages=2,
            storage_path=f"storage/companies/C00000_SAMPLE/{test_doc_type}/05_archive/2026-08/raw",
            file_hash=file_hash
        )
        self.assertTrue(success)

        # 2. Check Duplicate
        is_dup, meta = check_duplicate_document(file_hash)
        self.assertTrue(is_dup)
        self.assertEqual(meta["batch_id"], batch_id)
        self.assertEqual(meta["original_filename"], "test_document.pdf")

        # 3. Create Pages
        p1 = create_page("page_1", batch_id, 1, f"storage/companies/C00000_SAMPLE/{test_doc_type}/03_preprocess/p1.png", "PENDING")
        p2 = create_page("page_2", batch_id, 2, f"storage/companies/C00000_SAMPLE/{test_doc_type}/03_preprocess/p2.png", "PENDING")
        self.assertTrue(p1)
        self.assertTrue(p2)

        # 4. Create Document
        doc_id = "test_doc_456"
        success = create_document(
            document_id=doc_id,
            batch_id=batch_id,
            doc_type_id=test_doc_type,
            source_id=test_source,
            status_code="PROCESSED",
            doc_number="DOC-001",
            doc_date="2026-08-15",
            entity_name="Test Vendor Inc.",
            total_amount=120.0,
            search_text="test tax invoice document",
            data_payload='{"net_amount": 120.0}'
        )
        self.assertTrue(success)

        # Link pages to document using ORM helper
        link_pages_to_document(doc_id, ["page_1", "page_2"])

        # 5. Fetch Document & Pages
        doc = get_document_by_id(doc_id)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["doc_number"], "DOC-001")
        self.assertEqual(doc["total_amount"], 120.0)
        self.assertEqual(doc["status_code"], "PROCESSED")

        pages = get_document_pages(doc_id)
        self.assertEqual(len(pages), 2)

        # 6. Fetch pending documents
        pending = get_pending_documents(test_doc_type)
        self.assertGreater(len(pending), 0)
        self.assertEqual(pending[0]["document_id"], doc_id)

    def test_03_status_updates(self):
        """Test approval and failure transitions with generic mock parameters."""
        batch_id = "test_batch_123"
        doc_id = "test_doc_456"

        doc_types = get_doc_types()
        test_doc_type = doc_types[0]["doc_type_id"] if doc_types else "expense_receipt"
        sources = get_sources(test_doc_type)
        test_source = sources[0]["source_id"] if sources else "NO_TAXID"

        # Ensure document exists
        create_document(
            document_id=doc_id,
            batch_id=batch_id,
            doc_type_id=test_doc_type,
            source_id=test_source,
            status_code="PROCESSED",
            doc_number="DOC-001",
            doc_date="2026-08-15",
            entity_name="Test Vendor Inc.",
            total_amount=120.0,
            search_text="test tax invoice document",
            data_payload='{"net_amount": 120.0}'
        )

        # Update payload (simulate human edit in Review UI)
        success = update_document_payload(
            document_id=doc_id,
            data_payload='{"net_amount": 110.0}',
            status_code="PROCESSED",
            doc_number="DOC-001-REV",
            doc_date="2026-08-15",
            entity_name="Test Vendor Corp.",
            total_amount=110.0,
            is_manually_edited=1
        )
        self.assertTrue(success)

        doc = get_document_by_id(doc_id)
        self.assertEqual(doc["doc_number"], "DOC-001-REV")
        self.assertEqual(doc["total_amount"], 110.0)
        self.assertEqual(doc["is_manually_edited"], 1)

        # Approve Document
        success = update_document_to_approved(
            document_id=doc_id,
            doc_number="DOC-001-REV",
            doc_date="2026-08-15",
            entity_name="Test Vendor Corp.",
            total_amount=110.0,
            data_payload='{"net_amount": 110.0}',
            confirmed_by="test_user"
        )
        self.assertTrue(success)

        doc = get_document_by_id(doc_id)
        self.assertEqual(doc["status_code"], "APPROVED")
        self.assertEqual(doc["is_closed"], 1)
        self.assertEqual(doc["confirmed_by"], "test_user")

        # Verify it is no longer in pending documents list
        pending = get_pending_documents(test_doc_type)
        doc_ids = [d["document_id"] for d in pending]
        self.assertNotIn(doc_id, doc_ids)

    def test_04_admin_toggles(self):
        """Test toggling is_active for doc_types and sources dynamically."""
        doc_types = get_doc_types()
        self.assertGreater(len(doc_types), 0)
        test_doc_type = doc_types[0]["doc_type_id"]

        sources = get_sources(test_doc_type)
        self.assertGreater(len(sources), 0)
        target_src = sources[0]
        src_id = target_src["source_id"]

        # Check source active state before toggle
        initial_status = target_src["is_active"]
        new_status = 0 if initial_status == 1 else 1

        # Toggle status
        success = update_source_active_status(src_id, test_doc_type, new_status)
        self.assertTrue(success)

        # Verify status changed
        updated_sources = get_sources(test_doc_type)
        updated_src = [s for s in updated_sources if s["source_id"] == src_id][0]
        self.assertEqual(updated_src["is_active"], new_status)


class TestSQLAlchemyORM(unittest.TestCase):
    """
    Test suite for SQLAlchemy 2.0 ORM patterns, session lifecycles, and model relationships.
    """

    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        initialize_db_schema()

    def test_01_database_url_resolution(self):
        """Test database URL dynamic resolution."""
        url = get_database_url()
        self.assertTrue(url.startswith("sqlite:///"))

    def test_02_orm_session_create_and_query(self):
        """Test creating and querying records via SQLAlchemy ORM session."""
        batch_id = f"orm_batch_{uuid.uuid4().hex[:8]}"
        file_hash = f"hash_{uuid.uuid4().hex}"

        with get_db_session() as session:
            batch = ProcessedBatch(
                batch_id=batch_id,
                original_filename="test_orm_doc.pdf",
                total_pages=1,
                storage_path="storage/companies/C00000_SAMPLE/expense_receipt/03_preprocess",
                file_hash=file_hash,
                created_at=datetime.now(timezone.utc).isoformat()
            )
            session.add(batch)

        with get_db_session() as session:
            queried_batch = session.scalars(select(ProcessedBatch).filter_by(batch_id=batch_id)).first()
            self.assertIsNotNone(queried_batch)
            self.assertEqual(queried_batch.original_filename, "test_orm_doc.pdf")
            self.assertEqual(queried_batch.file_hash, file_hash)

    def test_03_orm_relationship_cascade(self):
        """Test ORM Merchant, ExpenseReceipt, and ExpenseReceiptItem relationships."""
        merchant_id = f"merch_{uuid.uuid4().hex[:8]}"

        with get_db_session() as session:
            merchant = Merchant(
                merchant_id=merchant_id,
                tax_id="9995561164871",
                merchant_name="ORM Test Merchant Co., Ltd.",
                short_name="orm_test",
                file_prefix="orm_test",
                status_code=MerchantStatus.APPROVED.value,
                default_wht_rate=0.0,
                is_vat_registered=1
            )
            session.add(merchant)

        with get_db_session() as session:
            fetched_merchant = session.scalars(select(Merchant).filter_by(merchant_id=merchant_id)).first()
            self.assertIsNotNone(fetched_merchant)
            self.assertEqual(fetched_merchant.merchant_name, "ORM Test Merchant Co., Ltd.")
            self.assertEqual(fetched_merchant.status_code, MerchantStatus.APPROVED.value)

    def test_04_sqlite_pragma_event_listener(self):
        """Test SQLite WAL mode and foreign keys are auto-enabled via connection listener."""
        from src.infrastructure.persistence.connection import get_engine
        engine = get_engine()
        with engine.connect() as conn:
            fk_res = conn.exec_driver_sql("PRAGMA foreign_keys;").scalar()
            self.assertEqual(fk_res, 1)

    def test_05_user_entity_crud_and_seed(self):
        """Test User entity seeding, creation, retrieval, and unique email validation."""
        from src.infrastructure.common.constants import SystemUserId, UserRole
        from src.infrastructure.persistence.seeder import seed_initial_data
        from src.infrastructure.persistence.masters import (
            create_user,
            get_user_by_id,
            get_user_by_email,
            list_users,
        )

        seed_initial_data()

        # 1. Verify default seeded users exist
        sys_user = get_user_by_id(SystemUserId.AUTO_SYSTEM)
        self.assertIsNotNone(sys_user)
        self.assertEqual(sys_user["role"], UserRole.SYSTEM.value)

        dev_admin = get_user_by_id(SystemUserId.DEV_ADMIN)
        self.assertIsNotNone(dev_admin)
        self.assertEqual(dev_admin["role"], UserRole.ADMIN.value)

        # 2. Create custom user with unique email
        test_email = f"reviewer_{uuid.uuid4().hex[:6]}@test.local"
        custom_user = create_user(
            email=test_email,
            full_name="Auditor One",
            role=UserRole.REVIEWER.value
        )
        self.assertIsNotNone(custom_user)
        self.assertEqual(custom_user["email"], test_email)
        self.assertEqual(custom_user["role"], UserRole.REVIEWER.value)

        # 3. Retrieve by email and list
        fetched = get_user_by_email(test_email)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["full_name"], "Auditor One")

        all_users = list_users()
        self.assertGreaterEqual(len(all_users), 3)

        # 4. Duplicate email fail-fast check
        with self.assertRaises(ValueError):
            create_user(
                email=test_email,
                full_name="Auditor Duplicate",
                role=UserRole.REVIEWER.value
            )

    def test_06_atomic_locking_concurrency(self):
        """Test atomic concurrency lock guard preventing double-approval and lost updates."""
        from src.infrastructure.common.constants import SystemUserId, DocumentStatusCode
        from src.infrastructure.persistence.documents import (
            create_batch,
            create_document,
            update_document_to_approved,
            update_document_to_rejected,
            update_document_payload,
            get_document_by_id,
        )

        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        create_batch(
            batch_id=batch_id,
            original_filename="concurrency_test.pdf",
            total_pages=1,
            storage_path="storage/companies/C00000_SAMPLE/expense_receipt/05_archive/raw",
            file_hash=f"hash_{uuid.uuid4().hex}"
        )

        create_document(
            document_id=doc_id,
            batch_id=batch_id,
            doc_type_id="expense_receipt",
            source_id="NO_TAXID",
            status_code=DocumentStatusCode.NEEDS_REVIEW,
            doc_number="CONC-001",
            doc_date="2026-08-24",
            entity_name="Initial Vendor",
            total_amount=500.0,
            search_text="concurrency test document",
            data_payload='{"net_amount": 500.0}'
        )

        # Step 1: User A approves the document successfully
        success_a = update_document_to_approved(
            document_id=doc_id,
            confirmed_by="usr_user_a",
            doc_number="CONC-001-A",
            total_amount=500.0
        )
        self.assertTrue(success_a)

        doc_after_a = get_document_by_id(doc_id)
        self.assertEqual(doc_after_a["is_closed"], 1)
        self.assertEqual(doc_after_a["status_code"], DocumentStatusCode.APPROVED)
        self.assertEqual(doc_after_a["confirmed_by"], "usr_user_a")

        # Step 2: User B tries to approve the already-closed document concurrently
        success_b = update_document_to_approved(
            document_id=doc_id,
            confirmed_by="usr_user_b",
            doc_number="CONC-001-B",
            total_amount=999.0
        )
        self.assertFalse(success_b, "Guard must reject double-approval on closed document.")

        # Step 3: User B tries to update payload on the closed document
        payload_update_success = update_document_payload(
            document_id=doc_id,
            entity_name="Hijacked Vendor",
            total_amount=999.0
        )
        self.assertFalse(payload_update_success, "Guard must reject payload update on closed document.")

        # Step 4: User B tries to reject the closed document
        reject_success = update_document_to_rejected(
            document_id=doc_id,
            reason="Late rejection attempt",
            confirmed_by="usr_user_b"
        )
        self.assertFalse(reject_success, "Guard must reject status alteration on closed document.")

        # Step 5: Verify original User A state remains 100% intact
        final_doc = get_document_by_id(doc_id)
        self.assertEqual(final_doc["confirmed_by"], "usr_user_a")
        self.assertEqual(final_doc["total_amount"], 500.0)
        self.assertEqual(final_doc["doc_number"], "CONC-001-A")

    def test_07_airline_ticket_hold_concurrency_and_ttl(self):
        """
        Test Airline Ticket Hold pattern (15-min TTL, renew heartbeat, and auto-release on expiration).
        """
        from datetime import datetime, timezone, timedelta
        from src.infrastructure.common.constants import DocumentStatusCode
        from src.infrastructure.persistence.connection import get_db_session
        from src.infrastructure.persistence.models import Document
        from src.infrastructure.persistence.documents import (
            create_batch,
            create_document,
            acquire_document_lock,
            renew_document_lock,
            release_document_lock,
            get_document_lock_status,
            update_document_to_approved,
        )

        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        create_batch(
            batch_id=batch_id,
            original_filename="ticket_hold_test.pdf",
            total_pages=1,
            storage_path="storage/companies/C00000_SAMPLE/expense_receipt/05_archive/raw",
            file_hash=f"hash_{uuid.uuid4().hex}"
        )

        create_document(
            document_id=doc_id,
            batch_id=batch_id,
            doc_type_id="expense_receipt",
            source_id="NO_TAXID",
            status_code=DocumentStatusCode.NEEDS_REVIEW,
            doc_number="HOLD-001",
            doc_date="2026-08-24",
            entity_name="Ticket Vendor",
            total_amount=1500.0,
            search_text="ticket hold test document",
            data_payload='{"net_amount": 1500.0}'
        )

        # 1. User A acquires exclusive 15-minute lock (900 seconds)
        success_a, msg_a, _ = acquire_document_lock(doc_id, user_id="usr_user_a", ttl_seconds=900)
        self.assertTrue(success_a)
        self.assertEqual(msg_a, "LOCK_ACQUIRED")

        status = get_document_lock_status(doc_id, ttl_seconds=900)
        self.assertTrue(status["is_locked"])
        self.assertEqual(status["locked_by"], "usr_user_a")
        self.assertGreater(status["remaining_seconds"], 880.0)
        self.assertFalse(status["is_expired"])

        # 2. User B tries to acquire the same document -> Rejected
        success_b, msg_b, _ = acquire_document_lock(doc_id, user_id="usr_user_b", ttl_seconds=900)
        self.assertFalse(success_b)
        self.assertEqual(msg_b, "LOCKED_BY_usr_user_a")

        # 3. Heartbeat / Extension Renewal
        renew_b = renew_document_lock(doc_id, user_id="usr_user_b", ttl_seconds=900)
        self.assertFalse(renew_b, "Non-owner cannot renew lock")

        renew_a = renew_document_lock(doc_id, user_id="usr_user_a", ttl_seconds=900)
        self.assertTrue(renew_a, "Owner can renew lock")

        # 4. TTL Expiration & Auto-Release (Inject past timestamp 16 minutes ago)
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()
        with get_db_session() as session:
            doc = session.scalars(select(Document).filter_by(document_id=doc_id)).first()
            doc.locked_at = stale_time

        status_stale = get_document_lock_status(doc_id, ttl_seconds=900)
        self.assertTrue(status_stale["is_expired"])
        self.assertEqual(status_stale["remaining_seconds"], 0.0)

        # User B now acquires the expired document -> Auto-Release grants lock to User B
        success_b_takeover, msg_b_takeover, _ = acquire_document_lock(doc_id, user_id="usr_user_b", ttl_seconds=900)
        self.assertTrue(success_b_takeover, "Auto-Release must allow User B to acquire expired lock")
        self.assertEqual(msg_b_takeover, "LOCK_ACQUIRED")

        status_b = get_document_lock_status(doc_id, ttl_seconds=900)
        self.assertEqual(status_b["locked_by"], "usr_user_b")
        self.assertTrue(status_b["is_locked"])

        # 5. Voluntary Release
        rel_success = release_document_lock(doc_id, user_id="usr_user_b")
        self.assertTrue(rel_success)

        status_unlocked = get_document_lock_status(doc_id, ttl_seconds=900)
        self.assertFalse(status_unlocked["is_locked"])
        self.assertIsNone(status_unlocked["locked_by"])

        # 6. Closed Document Lock Protection
        update_document_to_approved(doc_id, confirmed_by="usr_admin", total_amount=1500.0)
        success_on_closed, msg_closed, _ = acquire_document_lock(doc_id, user_id="usr_user_a")
        self.assertFalse(success_on_closed)
        self.assertEqual(msg_closed, "DOCUMENT_ALREADY_CLOSED")

    def test_09_document_schema_modernization(self):
        """Test that Document uses doc_type_id and merchant_id (with relationship to Merchant)."""
        merch_id = f"merch_{uuid.uuid4().hex[:8]}"
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        with get_db_session() as session:
            merchant = Merchant(
                merchant_id=merch_id,
                tax_id="0107542000011",
                merchant_name="CP ALL PUBLIC CO., LTD.",
                short_name="7eleven",
                file_prefix="7eleven",
                status_code=MerchantStatus.APPROVED.value
            )
            batch = ProcessedBatch(
                batch_id=batch_id,
                original_filename="receipt.pdf",
                total_pages=1,
                storage_path="/tmp/receipt.pdf",
                file_hash=f"hash_{uuid.uuid4().hex}"
            )
            doc = Document(
                document_id=doc_id,
                batch_id=batch_id,
                doc_type_id="expense_receipt",
                merchant_id=merch_id,
                status_code=DocumentStatusCode.PENDING,
                total_amount=150.0
            )
            session.add(merchant)
            session.add(batch)
            session.add(doc)

        with get_db_session() as session:
            saved_doc = session.scalars(select(Document).filter_by(document_id=doc_id)).first()
            self.assertIsNotNone(saved_doc)
            self.assertEqual(saved_doc.doc_type_id, "expense_receipt")
            self.assertEqual(saved_doc.merchant_id, merch_id)
            self.assertIsNotNone(saved_doc.merchant)
            self.assertEqual(saved_doc.merchant.short_name, "7eleven")


if __name__ == "__main__":
    unittest.main()


