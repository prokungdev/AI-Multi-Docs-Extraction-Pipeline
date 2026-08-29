"""Database schema initialization and seeding routines using SQLAlchemy 2.0 ORM."""

import os
from pathlib import Path
from src.infrastructure.core.logger import logger

from .engine import engine, get_engine, get_log_engine, get_db_session, PROJECT_ROOT
from .models import (
    Base,
    LogBase,
    Company,
    DocumentStatus,
    ExpenseReceiptItem,
    ExpenseReceipt,
    BatchPage,
    DocumentControl,
    Batch,
    Merchant,
    ApiCallLog,
    ApplicationLog
)
from src.infrastructure.core.constants import (
    DefaultCompany,
    DefaultIdentifier,
    DocumentStatusCode,
    EntityIdPrefix,
    generate_entity_id,
)


def initialize_log_db_schema(settings_path: str = "configs/settings.json"):
    """Initializes logging database schema in logs/logs.db via LogBase metadata."""
    try:
        current_log_engine = get_log_engine(settings_path)
        LogBase.metadata.create_all(current_log_engine)
    except Exception as e:
        logger.warning(f"Failed to initialize log database schema: {e}")


def initialize_db_schema(drop_and_recreate: bool = False):
    """Initializes database schema using SQLAlchemy 2.0 ORM Base metadata."""
    current_engine = get_engine()
    if drop_and_recreate:
        logger.info("Dropping and recreating all database tables...")
        Base.metadata.drop_all(current_engine)

    try:
        initialize_log_db_schema()

        with current_engine.connect() as conn:
            try:
                res = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
                existing_tables = set(r[0] for r in res.fetchall())
                if "processed_batches" in existing_tables and "batches" not in existing_tables:
                    conn.exec_driver_sql("ALTER TABLE processed_batches RENAME TO batches")
                if "document_pages" in existing_tables and "batch_pages" not in existing_tables:
                    conn.exec_driver_sql("ALTER TABLE document_pages RENAME TO batch_pages")
                if "extracted_documents" in existing_tables and "document_controls" not in existing_tables:
                    conn.exec_driver_sql("ALTER TABLE extracted_documents RENAME TO document_controls")
                if "documents" in existing_tables and "document_controls" not in existing_tables:
                    conn.exec_driver_sql("ALTER TABLE documents RENAME TO document_controls")
                conn.commit()
            except Exception as rename_err:
                logger.debug(f"Table rename check note: {rename_err}")

        Base.metadata.create_all(current_engine)

        with current_engine.connect() as conn:
            try:
                conn.exec_driver_sql("DROP TABLE IF EXISTS api_credentials")
                conn.exec_driver_sql("DROP TABLE IF EXISTS application_logs")
                conn.exec_driver_sql("DROP TABLE IF EXISTS document_sources")
            except Exception as drop_err:
                logger.debug(f"Note on dropping obsolete tables: {drop_err}")

            # Merchants migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(merchants)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "company_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN company_id VARCHAR(36)")
                if "short_name" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN short_name VARCHAR(100) DEFAULT 'merchant'")
                if "file_prefix" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN file_prefix VARCHAR(100) DEFAULT 'merchant'")
                if "status_code" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN status_code VARCHAR(50) DEFAULT 'APPROVED'")
                if "approved_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN approved_by VARCHAR(100)")
                if "approved_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN approved_at VARCHAR(50)")
                if "is_active" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN is_active INTEGER DEFAULT 1")
                if "updated_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN updated_at VARCHAR(50)")
            except Exception as mig_err:
                logger.debug(f"Merchants schema migration note: {mig_err}")

            # DocumentControls migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(document_controls)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "domain_id" in existing_cols and "doc_type_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls RENAME COLUMN domain_id TO doc_type_id")
                elif "doc_type_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN doc_type_id VARCHAR(100)")

                if "company_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN company_id VARCHAR(36)")
                if "is_closed" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN is_closed INTEGER DEFAULT 0")
                if "is_locked" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN is_locked INTEGER DEFAULT 0")
                if "locked_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN locked_by VARCHAR(36)")
                if "locked_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN locked_at VARCHAR(50)")
                if "is_auto_approved" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN is_auto_approved INTEGER DEFAULT 0")
                if "is_ambiguous" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN is_ambiguous INTEGER")
                if "cost_usd" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN cost_usd FLOAT DEFAULT 0.0")
                if "cost_thb" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN cost_thb FLOAT DEFAULT 0.0")
                if "is_free_tier" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN is_free_tier INTEGER DEFAULT 0")
            except Exception as mig_err:
                logger.debug(f"DocumentControls schema migration note: {mig_err}")

            # Batches migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(batches)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "company_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE batches ADD COLUMN company_id VARCHAR(36)")
                if "original_filename" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE batches ADD COLUMN original_filename VARCHAR(255) DEFAULT 'document.pdf'")
            except Exception as mig_err:
                logger.debug(f"Batches schema migration note: {mig_err}")

            # Expense receipts migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(expense_receipts)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "company_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE expense_receipts ADD COLUMN company_id VARCHAR(36)")
                if "doc_number" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE expense_receipts ADD COLUMN doc_number VARCHAR(100)")
            except Exception as mig_err:
                logger.debug(f"Expense Receipts schema migration note: {mig_err}")

            # Api call logs migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(api_call_logs)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "company_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE api_call_logs ADD COLUMN company_id VARCHAR(36)")
                if "cost_usd" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE api_call_logs ADD COLUMN cost_usd FLOAT DEFAULT 0.0")
                if "nominal_value_usd" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE api_call_logs ADD COLUMN nominal_value_usd FLOAT DEFAULT 0.0")
                if "is_free_tier" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE api_call_logs ADD COLUMN is_free_tier INTEGER DEFAULT 0")
            except Exception as mig_err:
                logger.debug(f"Api Call Logs schema migration note: {mig_err}")

            # Batch pages migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(batch_pages)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "chunk_index" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE batch_pages ADD COLUMN chunk_index INTEGER DEFAULT 1")
            except Exception as mig_err:
                logger.debug(f"Batch Pages schema migration note: {mig_err}")

            conn.commit()

        logger.info("Relational database schema initialized successfully via SQLAlchemy Base metadata.")
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        raise e


def reset_pipeline_database(clear_documents_only: bool = False) -> dict:
    """Safely resets pipeline database."""
    from .engine import get_database_url, dispose_all_engines
    from .seeder import seed_initial_data
    from sqlalchemy import delete

    try:
        if not clear_documents_only:
            url = get_database_url()
            if url.startswith("sqlite:///"):
                db_path = url.replace("sqlite:///", "")
                dispose_all_engines()
                if os.path.exists(db_path):
                    try:
                        os.remove(db_path)
                    except Exception as fe:
                        logger.warning(f"Could not remove database file '{db_path}': {fe}")
                for suffix in ["-wal", "-shm"]:
                    if os.path.exists(db_path + suffix):
                        try:
                            os.remove(db_path + suffix)
                        except Exception:
                            pass

            initialize_db_schema(drop_and_recreate=True)
            seed_initial_data()
            return {"status": "SUCCESS", "action": "DROPPED_DATABASE_AND_RESEEDED"}

        deleted_counts = {}
        with get_db_session() as session:
            models_to_clear = [
                ("expense_receipt_items", ExpenseReceiptItem),
                ("expense_receipts", ExpenseReceipt),
                ("batch_pages", BatchPage),
                ("document_controls", DocumentControl),
                ("batches", Batch),
                ("api_call_logs", ApiCallLog)
            ]
            for tbl_name, model_cls in models_to_clear:
                res = session.execute(delete(model_cls))
                deleted_counts[tbl_name] = res.rowcount

        return {"status": "SUCCESS", "cleared_tables": deleted_counts}
    except Exception as e:
        logger.error(f"Failed to reset pipeline database: {e}")
        return {"status": "ERROR", "error": str(e)}
