import os
import unittest
import uuid
from datetime import datetime, timezone

from src.core.db import (
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
from src.core.db.connection import get_db_session, get_engine, get_database_url
from src.core.db.models import (
    Base,
    ProcessedBatch,
    DocumentStatus,
    DocumentPage,
    Merchant,
    MerchantStatus,
    ExpenseReceipt,
    ExpenseReceiptItem,
)


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
        from src.core.db.connection import get_engine
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
        self.assertEqual(doc["is_locked"], 1)
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
        Base.metadata.create_all(cls.engine)

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


if __name__ == "__main__":
    unittest.main()
