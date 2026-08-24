"""Database schema initialization and seeding routines using SQLAlchemy 2.0 ORM."""

import os
from pathlib import Path
from src.infrastructure.common.logger import logger

from .connection import engine, get_engine, get_log_engine, get_db_session, PROJECT_ROOT
from .models import (
    Base,
    LogBase,
    Company,
    DocumentStatus,
    ExpenseReceiptItem,
    ExpenseReceipt,
    DocumentPage,
    Document,
    ProcessedBatch,
    Merchant,
    ApiCallLog,
    ApplicationLog
)
from src.infrastructure.common.constants import (
    DefaultCompany,
    DefaultIdentifier,
    DocumentStatusCode,
    EntityIdPrefix,
    generate_entity_id,
)


def initialize_log_db_schema(settings_path: str = "configs/settings.json"):
    """
    Initializes the logging database schema in logs/logs.db via LogBase metadata.
    """
    try:
        current_log_engine = get_log_engine(settings_path)
        LogBase.metadata.create_all(current_log_engine)
    except Exception as e:
        logger.warning(f"Failed to initialize log database schema: {e}")


def initialize_db_schema(drop_and_recreate: bool = False):
    """
    Creates relational database schema for all operational models via SQLAlchemy Base Metadata
    and performs lightweight schema migrations for newly added columns.
    If drop_and_recreate is True, drops all operational tables first for a clean fresh start.
    """
    try:
        current_engine = get_engine()
        if drop_and_recreate:
            logger.warning("Dropping all existing operational database tables for clean fresh start...")
            with current_engine.connect() as conn:
                if str(current_engine.url).startswith("sqlite"):
                    res = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
                    all_tables = [r[0] for r in res.fetchall()]
                    conn.exec_driver_sql("PRAGMA foreign_keys = OFF;")
                    for t in all_tables:
                        conn.exec_driver_sql(f"DROP TABLE IF EXISTS {t}")
                    conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
                else:
                    Base.metadata.drop_all(current_engine)

        Base.metadata.create_all(current_engine)

        with current_engine.connect() as conn:
            # Drop obsolete/dormant tables and segregated tables from operational database
            try:
                conn.exec_driver_sql("DROP TABLE IF EXISTS api_credentials")
                conn.exec_driver_sql("DROP TABLE IF EXISTS application_logs")
                conn.exec_driver_sql("DROP TABLE IF EXISTS document_sources")
            except Exception as drop_err:
                logger.debug(f"Note on dropping obsolete tables: {drop_err}")

            # 1. Merchants table migrations
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

            # 2. Documents table migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(documents)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "domain_id" in existing_cols and "doc_type_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents RENAME COLUMN domain_id TO doc_type_id")
                elif "doc_type_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN doc_type_id VARCHAR(100) DEFAULT 'expense_receipt'")

                if "source_id" in existing_cols and "merchant_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents RENAME COLUMN source_id TO merchant_id")
                elif "merchant_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN merchant_id VARCHAR(36)")

                if "company_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN company_id VARCHAR(36)")
                if "is_closed" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN is_closed INTEGER DEFAULT 0")
                if "is_locked" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN is_locked INTEGER DEFAULT 0")
                if "locked_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN locked_by VARCHAR(36)")
                if "locked_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN locked_at VARCHAR(50)")
                if "is_auto_approved" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN is_auto_approved INTEGER DEFAULT 0")
                if "is_ambiguous" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN is_ambiguous INTEGER")
                if "cost_usd" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN cost_usd FLOAT DEFAULT 0.0")
                if "cost_thb" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN cost_thb FLOAT DEFAULT 0.0")
                if "is_free_tier" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN is_free_tier INTEGER DEFAULT 0")
            except Exception as mig_err:
                logger.debug(f"Documents schema migration note: {mig_err}")

            # 3. Processed batches table migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(processed_batches)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "company_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE processed_batches ADD COLUMN company_id VARCHAR(36)")
                if "original_filename" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE processed_batches ADD COLUMN original_filename VARCHAR(255) DEFAULT 'document.pdf'")
            except Exception as mig_err:
                logger.debug(f"Processed Batches schema migration note: {mig_err}")

            # 4. Expense receipts table migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(expense_receipts)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "company_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE expense_receipts ADD COLUMN company_id VARCHAR(36)")
            except Exception as mig_err:
                logger.debug(f"Expense Receipts schema migration note: {mig_err}")

            # 5. Api call logs table migrations
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

            # 6. Document pages table migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(document_pages)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "chunk_index" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_pages ADD COLUMN chunk_index INTEGER DEFAULT 1")
            except Exception as mig_err:
                logger.debug(f"Document Pages schema migration note: {mig_err}")

            conn.commit()

        logger.info("Relational database schema initialized successfully via SQLAlchemy Base metadata.")
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        raise e


def reset_pipeline_database(clear_documents_only: bool = True) -> dict:
    """
    Safely resets pipeline database tables using Pure SQLAlchemy 2.0 ORM.
    """
    from sqlalchemy import delete
    try:
        deleted_counts = {}
        with get_db_session() as session:
            models_to_clear = [
                ("expense_receipt_items", ExpenseReceiptItem),
                ("expense_receipts", ExpenseReceipt),
                ("document_pages", DocumentPage),
                ("documents", Document),
                ("processed_batches", ProcessedBatch),
                ("api_call_logs", ApiCallLog)
            ]
            for tbl_name, model_cls in models_to_clear:
                res = session.execute(delete(model_cls))
                deleted_counts[tbl_name] = res.rowcount

        return {"status": "SUCCESS", "cleared_tables": deleted_counts}
    except Exception as e:
        logger.error(f"Failed to reset pipeline database: {e}")
        return {"status": "ERROR", "error": str(e)}

