import os
import unittest
import uuid
from datetime import datetime, timezone
from src.core.db.connection import get_db_session, get_engine, get_database_url
from src.core.db.models import Base, ProcessedBatch, DocumentStatus, DocumentPage, MerchantMaster, ExpenseReceipt

class TestSQLAlchemyORM(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Create tables for ORM testing."""
        cls.engine = get_engine()
        Base.metadata.create_all(cls.engine)

    def test_01_database_url_resolution(self):
        """Test database URL dynamic resolution."""
        url = get_database_url()
        self.assertTrue(url.startswith("sqlite:///"))
        print(f"[TEST] Database URL resolution passed: {url}")

    def test_02_orm_session_create_and_query(self):
        """Test creating and querying records via SQLAlchemy ORM session."""
        batch_id = f"orm_batch_{uuid.uuid4().hex[:8]}"
        file_hash = f"hash_{uuid.uuid4().hex}"

        with get_db_session() as session:
            # 1. Insert ProcessedBatch ORM entity
            batch = ProcessedBatch(
                batch_id=batch_id,
                original_pdf_name="test_orm_doc.pdf",
                total_pages=1,
                storage_path="pipeline_storage/expense_receipt/02_split_pages",
                file_hash=file_hash,
                created_at=datetime.now(timezone.utc).isoformat()
            )
            session.add(batch)

        # 2. Query back in a new session
        with get_db_session() as session:
            queried_batch = session.query(ProcessedBatch).filter_by(batch_id=batch_id).first()
            self.assertIsNotNone(queried_batch)
            self.assertEqual(queried_batch.original_pdf_name, "test_orm_doc.pdf")
            self.assertEqual(queried_batch.file_hash, file_hash)
            print(f"[TEST] ORM Batch insertion & query test passed for batch '{batch_id}'.")

    def test_03_orm_relationship_cascade(self):
        """Test ORM MerchantMaster and ExpenseReceipt relationship."""
        merchant_id = f"merch_{uuid.uuid4().hex[:8]}"

        with get_db_session() as session:
            merchant = MerchantMaster(
                merchant_id=merchant_id,
                tax_id="9995561164871",
                merchant_name="ORM Test Merchant Co., Ltd.",
                default_wht_rate=0.0,
                is_vat_registered=1
            )
            session.add(merchant)

        with get_db_session() as session:
            fetched_merchant = session.query(MerchantMaster).filter_by(merchant_id=merchant_id).first()
            self.assertIsNotNone(fetched_merchant)
            self.assertEqual(fetched_merchant.merchant_name, "ORM Test Merchant Co., Ltd.")
            print(f"[TEST] ORM MerchantMaster relationship test passed for merchant '{merchant_id}'.")

if __name__ == "__main__":
    unittest.main()
