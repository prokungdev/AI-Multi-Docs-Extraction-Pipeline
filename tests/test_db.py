import os
import sqlite3
import unittest
from datetime import datetime
from src.core.db import (
    get_db_connection,
    initialize_db_schema,
    seed_initial_data,
    create_batch,
    create_page,
    create_document,
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
        import os
        cls.db_path = "pipeline_storage/test_pipeline.db"
        os.environ["DB_PATH_OVERRIDE"] = cls.db_path
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
            
    @classmethod
    def tearDownClass(cls):
        # Clean up the test database file
        import os
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        os.environ.pop("DB_PATH_OVERRIDE", None)

    def test_01_init_and_seed(self):
        """Test database schema initialization and seeding."""
        initialize_db_schema()
        # Verify db file is created
        self.assertTrue(os.path.exists(self.db_path))
        
        seed_initial_data()
        
        # Verify default domains and sources are seeded
        domains = get_domains()
        self.assertGreater(len(domains), 0)
        self.assertEqual(domains[0]["domain_id"], "expense_receipt")
        
        sources = get_sources("expense_receipt")
        self.assertGreater(len(sources), 0)
        source_ids = [s["source_id"] for s in sources]
        self.assertIn("spx_express", source_ids)
        self.assertIn("shopee_thailand", source_ids)
        self.assertIn("grab_thailand", source_ids)
        self.assertIn("_default", source_ids)

    def test_02_crud_operations(self):
        """Test batch, page, and document CRUD flows."""
        batch_id = "test_batch_123"
        file_hash = "mock_sha256_hash_value"
        
        # 1. Create Batch
        success = create_batch(
            batch_id=batch_id,
            original_pdf_name="test_receipt.pdf",
            total_pages=2,
            storage_path="pipeline_storage/expense_receipt/04_archive/2026-08/raw",
            file_hash=file_hash
        )
        self.assertTrue(success)
        
        # 2. Check Duplicate
        is_dup, meta = check_duplicate_document(file_hash)
        self.assertTrue(is_dup)
        self.assertEqual(meta["batch_id"], batch_id)
        self.assertEqual(meta["original_pdf_name"], "test_receipt.pdf")
        
        # 3. Create Pages
        p1 = create_page("page_1", batch_id, 1, "pipeline_storage/expense_receipt/02_split_pages/p1.png", "PENDING")
        p2 = create_page("page_2", batch_id, 2, "pipeline_storage/expense_receipt/02_split_pages/p2.png", "PENDING")
        self.assertTrue(p1)
        self.assertTrue(p2)
        
        # 4. Create Document
        doc_id = "test_doc_456"
        success = create_document(
            document_id=doc_id,
            batch_id=batch_id,
            domain_id="expense_receipt",
            source_id="spx_express",
            status_code="PROCESSED",
            doc_number="SPX-001",
            doc_date="2026-08-15",
            entity_name="SPX Express",
            total_amount=120.0,
            search_text="spx express tax invoice",
            data_payload='{"net_amount": 120.0}'
        )
        self.assertTrue(success)
        
        # Link pages to document
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE document_pages SET document_id = ? WHERE batch_id = ?", (doc_id, batch_id))
        conn.commit()
        conn.close()
        
        # 5. Fetch Document & Pages
        doc = get_document_by_id(doc_id)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["doc_number"], "SPX-001")
        self.assertEqual(doc["total_amount"], 120.0)
        self.assertEqual(doc["status_code"], "PROCESSED")
        
        pages = get_document_pages(doc_id)
        self.assertEqual(len(pages), 2)
        
        # 6. Fetch pending documents
        pending = get_pending_documents("expense_receipt")
        self.assertGreater(len(pending), 0)
        self.assertEqual(pending[0]["document_id"], doc_id)

    def test_03_status_updates(self):
        """Test approval and failure transitions."""
        batch_id = "test_batch_123"
        doc_id = "test_doc_456"
        
        # Ensure document exists
        create_document(
            document_id=doc_id,
            batch_id=batch_id,
            domain_id="expense_receipt",
            source_id="spx_express",
            status_code="PROCESSED",
            doc_number="SPX-001",
            doc_date="2026-08-15",
            entity_name="SPX Express",
            total_amount=120.0,
            search_text="spx express tax invoice",
            data_payload='{"net_amount": 120.0}'
        )
        
        # Update payload (simulate human edit in Review UI)
        success = update_document_payload(
            document_id=doc_id,
            data_payload='{"net_amount": 110.0}',
            status_code="PROCESSED",
            doc_number="SPX-001-REV",
            doc_date="2026-08-15",
            entity_name="SPX Express Co.",
            total_amount=110.0,
            is_manually_edited=1
        )
        self.assertTrue(success)
        
        doc = get_document_by_id(doc_id)
        self.assertEqual(doc["doc_number"], "SPX-001-REV")
        self.assertEqual(doc["total_amount"], 110.0)
        self.assertEqual(doc["is_manually_edited"], 1)
        
        # Approve Document
        success = update_document_to_approved(
            document_id=doc_id,
            doc_number="SPX-001-REV",
            doc_date="2026-08-15",
            entity_name="SPX Express Co.",
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
        pending = get_pending_documents("expense_receipt")
        doc_ids = [d["document_id"] for d in pending]
        self.assertNotIn(doc_id, doc_ids)

    def test_04_admin_toggles(self):
        """Test toggling is_active for domains and sources."""
        # Check source active state before toggle
        sources = get_sources("expense_receipt")
        grab_src = [s for s in sources if s["source_id"] == "grab_thailand"][0]
        self.assertEqual(grab_src["is_active"], 1)
        
        # Deactivate
        success = update_source_active_status("grab_thailand", 0)
        self.assertTrue(success)
        
        sources = get_sources("expense_receipt")
        grab_src = [s for s in sources if s["source_id"] == "grab_thailand"][0]
        self.assertEqual(grab_src["is_active"], 0)

if __name__ == "__main__":
    unittest.main()
