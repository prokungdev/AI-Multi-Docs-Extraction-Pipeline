import os
import unittest
from datetime import datetime
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
    get_domains,
    get_sources,
    update_domain_active_status,
    update_source_active_status
)


class TestDatabase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Override connection to use a temporary test file db
        cls.db_path = "storage/test_pipeline.db"
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    @classmethod
    def tearDownClass(cls):
        # Clean up the test database file and dispose SQLAlchemy engine
        from src.core.db.connection import get_engine
        try:
            get_engine().dispose()
        except Exception:
            pass
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

        # Verify default domains and sources are seeded dynamically
        domains = get_domains()
        self.assertGreater(len(domains), 0)
        domain_id = domains[0]["domain_id"]

        sources = get_sources(domain_id)
        self.assertGreater(len(sources), 0)
        source_ids = [s["source_id"] for s in sources]
        self.assertIn("_default", source_ids)

    def test_02_crud_operations(self):
        """Test batch, page, and document CRUD flows using generic test identifiers."""
        batch_id = "test_batch_123"
        file_hash = "mock_sha256_hash_value"

        # Resolve active domain & source dynamically
        domains = get_domains()
        test_domain = domains[0]["domain_id"] if domains else "test_domain"
        sources = get_sources(test_domain)
        test_source = sources[0]["source_id"] if sources else "_default"

        # 1. Create Batch
        success = create_batch(
            batch_id=batch_id,
            original_filename="test_document.pdf",
            total_pages=2,
            storage_path=f"storage/{test_domain}/05_archive/2026-08/raw",
            file_hash=file_hash
        )
        self.assertTrue(success)

        # 2. Check Duplicate
        is_dup, meta = check_duplicate_document(file_hash)
        self.assertTrue(is_dup)
        self.assertEqual(meta["batch_id"], batch_id)
        self.assertEqual(meta["original_filename"], "test_document.pdf")

        # 3. Create Pages
        p1 = create_page("page_1", batch_id, 1, f"storage/{test_domain}/03_preprocess/p1.png", "PENDING")
        p2 = create_page("page_2", batch_id, 2, f"storage/{test_domain}/03_preprocess/p2.png", "PENDING")
        self.assertTrue(p1)
        self.assertTrue(p2)

        # 4. Create Document
        doc_id = "test_doc_456"
        success = create_document(
            document_id=doc_id,
            batch_id=batch_id,
            domain_id=test_domain,
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
        pending = get_pending_documents(test_domain)
        self.assertGreater(len(pending), 0)
        self.assertEqual(pending[0]["document_id"], doc_id)

    def test_03_status_updates(self):
        """Test approval and failure transitions with generic mock parameters."""
        batch_id = "test_batch_123"
        doc_id = "test_doc_456"

        domains = get_domains()
        test_domain = domains[0]["domain_id"] if domains else "test_domain"
        sources = get_sources(test_domain)
        test_source = sources[0]["source_id"] if sources else "_default"

        # Ensure document exists
        create_document(
            document_id=doc_id,
            batch_id=batch_id,
            domain_id=test_domain,
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
        pending = get_pending_documents(test_domain)
        doc_ids = [d["document_id"] for d in pending]
        self.assertNotIn(doc_id, doc_ids)

    def test_04_admin_toggles(self):
        """Test toggling is_active for domains and sources dynamically."""
        domains = get_domains()
        self.assertGreater(len(domains), 0)
        test_domain = domains[0]["domain_id"]

        sources = get_sources(test_domain)
        self.assertGreater(len(sources), 0)
        target_src = sources[0]
        src_id = target_src["source_id"]

        # Check source active state before toggle
        initial_status = target_src["is_active"]
        new_status = 0 if initial_status == 1 else 1

        # Toggle status
        success = update_source_active_status(src_id, test_domain, new_status)
        self.assertTrue(success)

        # Verify status changed
        updated_sources = get_sources(test_domain)
        updated_src = [s for s in updated_sources if s["source_id"] == src_id][0]
        self.assertEqual(updated_src["is_active"], new_status)


if __name__ == "__main__":
    unittest.main()
