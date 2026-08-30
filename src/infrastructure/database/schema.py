"""Database schema initialization and seeding routines using SQLAlchemy 2.0 ORM."""

import os
from pathlib import Path
from src.infrastructure.core.logger import logger

from .engine import engine, get_engine, get_log_engine, get_db_session, PROJECT_ROOT
from .models import (
    Base,
    LogBase,
    Role,
    Company,
    User,
    UserCompany,
    DocumentStatus,
    DocumentType,
    AIModelConfig,
    ExpenseReceiptItem,
    ExpenseReceipt,
    BatchPage,
    DocumentControl,
    Batch,
    Merchant,
    IntegrationMethod,
    TargetSystem,
    VoucherStatus,
    ConsolidateMode,
    ExpenseType,
    ExpenseAccountMapping,
    JournalVoucher,
    JournalVoucherItem,
    ApiCallLog,
    ApplicationLog
)
from src.infrastructure.core.constants import (
    DefaultCompany,
    DefaultIdentifier,
    DocumentStatusCode,
    EntityIdPrefix,
    SystemUserId,
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

            # Roles migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(roles)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "updated_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE roles ADD COLUMN updated_at VARCHAR(50)")
                if "updated_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE roles ADD COLUMN updated_by VARCHAR(36)")
            except Exception as mig_err:
                logger.debug(f"Roles schema migration note: {mig_err}")

            # Users migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(users)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "password_hash" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)")
                if "created_by" not in existing_cols:
                    conn.exec_driver_sql(f"ALTER TABLE users ADD COLUMN created_by VARCHAR(36) DEFAULT '{SystemUserId.SYSTEM_ADMIN}'")
                if "updated_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN updated_by VARCHAR(36)")
                if "updated_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN updated_at VARCHAR(50)")
            except Exception as mig_err:
                logger.debug(f"Users schema migration note: {mig_err}")

            # User Companies migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(user_companies)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "updated_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE user_companies ADD COLUMN updated_at VARCHAR(50)")
                if "updated_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE user_companies ADD COLUMN updated_by VARCHAR(36)")
            except Exception as mig_err:
                logger.debug(f"UserCompanies schema migration note: {mig_err}")

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
                if "vendor_code" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN vendor_code VARCHAR(50)")
                if "default_expense_type" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN default_expense_type VARCHAR(100)")
                if "consolidate_mode" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN consolidate_mode VARCHAR(50) DEFAULT 'BY_MERCHANT'")
                if "default_vat_type" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN default_vat_type VARCHAR(20) DEFAULT 'EXCLUSIVE'")
                if "has_wht" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN has_wht INTEGER DEFAULT 0")
                if "status_code" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN status_code VARCHAR(50) DEFAULT 'APPROVED'")
                if "approved_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN approved_by VARCHAR(100)")
                if "approved_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN approved_at VARCHAR(50)")
                if "is_active" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN is_active INTEGER DEFAULT 1")
                if "is_override_vat" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN is_override_vat INTEGER DEFAULT 1")
                if "created_by" not in existing_cols:
                    conn.exec_driver_sql(f"ALTER TABLE merchants ADD COLUMN created_by VARCHAR(36) DEFAULT '{SystemUserId.SYSTEM_ADMIN}'")
                if "updated_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN updated_by VARCHAR(36)")
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
                if "created_by" not in existing_cols:
                    conn.exec_driver_sql(f"ALTER TABLE document_controls ADD COLUMN created_by VARCHAR(36) DEFAULT '{SystemUserId.AUTO_SYSTEM}'")
                if "updated_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE document_controls ADD COLUMN updated_by VARCHAR(36)")
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
                if "created_by" not in existing_cols:
                    conn.exec_driver_sql(f"ALTER TABLE batches ADD COLUMN created_by VARCHAR(36) DEFAULT '{SystemUserId.AUTO_SYSTEM}'")
                if "updated_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE batches ADD COLUMN updated_by VARCHAR(36)")
                if "updated_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE batches ADD COLUMN updated_at VARCHAR(50)")
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
                if "has_wht" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE expense_receipts ADD COLUMN has_wht INTEGER DEFAULT 0")
                if "wht_rate" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE expense_receipts ADD COLUMN wht_rate FLOAT DEFAULT 0.0")
                if "wht_amount" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE expense_receipts ADD COLUMN wht_amount FLOAT DEFAULT 0.0")
                if "created_by" not in existing_cols:
                    conn.exec_driver_sql(f"ALTER TABLE expense_receipts ADD COLUMN created_by VARCHAR(36) DEFAULT '{SystemUserId.AUTO_SYSTEM}'")
                if "updated_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE expense_receipts ADD COLUMN updated_by VARCHAR(36)")
            except Exception as mig_err:
                logger.debug(f"Expense Receipts schema migration note: {mig_err}")

            # Companies migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(companies)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "created_by" not in existing_cols:
                    conn.exec_driver_sql(f"ALTER TABLE companies ADD COLUMN created_by VARCHAR(36) DEFAULT '{SystemUserId.SYSTEM_ADMIN}'")
                if "updated_by" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE companies ADD COLUMN updated_by VARCHAR(36)")
                if "ai_config_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE companies ADD COLUMN ai_config_id VARCHAR(50)")
                if "active_target_system_id" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE companies ADD COLUMN active_target_system_id VARCHAR(50) DEFAULT 'EXPRESS'")
                if "auto_gen_voucher_no" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE companies ADD COLUMN auto_gen_voucher_no INTEGER DEFAULT 1")
            except Exception as mig_err:
                logger.debug(f"Companies schema migration note: {mig_err}")

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

            # Journal Vouchers migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(journal_vouchers)")
                existing_cols = [row[1] for row in res.fetchall()]
                if existing_cols and "posted_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE journal_vouchers ADD COLUMN posted_at VARCHAR(50)")
                if existing_cols and "is_override_vat" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE journal_vouchers ADD COLUMN is_override_vat INTEGER DEFAULT 1")
            except Exception as mig_err:
                logger.debug(f"Journal Vouchers schema migration note: {mig_err}")

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
