"""Database schema initialization and seeding routines using SQLAlchemy 2.0 ORM."""

import os
from pathlib import Path
from loguru import logger

from .connection import engine, get_engine, get_db_session, PROJECT_ROOT
from .models import (
    Base,
    DocumentStatus,
    DocumentSource,
    ApiCredential,
    ExpenseReceiptItem,
    ExpenseReceipt,
    DocumentPage,
    Document,
    ProcessedBatch,
    Merchant,
    ApiCallLog,
    ApplicationLog
)


def initialize_log_db_schema(settings_path: str = "configs/settings.json"):
    """
    Initializes the logging database schema via Base metadata.
    """
    try:
        current_engine = get_engine()
        Base.metadata.create_all(current_engine)
    except Exception as e:
        logger.warning(f"Failed to initialize log database schema: {e}")


def initialize_db_schema():
    """
    Creates relational database schema for all models via SQLAlchemy Base Metadata
    and performs lightweight schema migrations for newly added columns.
    """
    try:
        current_engine = get_engine()
        Base.metadata.create_all(current_engine)

        with current_engine.connect() as conn:
            # 1. Merchants table migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(merchants)")
                existing_cols = [row[1] for row in res.fetchall()]
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
                if "updated_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE merchants ADD COLUMN updated_at VARCHAR(50)")
            except Exception as mig_err:
                logger.debug(f"Merchants schema migration note: {mig_err}")

            # 2. Api Credentials table migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(api_credentials)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "created_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE api_credentials ADD COLUMN created_at VARCHAR(50)")
                if "updated_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE api_credentials ADD COLUMN updated_at VARCHAR(50)")
            except Exception as mig_err:
                logger.debug(f"Api Credentials schema migration note: {mig_err}")

            # 3. Documents table migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(documents)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "is_auto_approved" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN is_auto_approved INTEGER DEFAULT 0")
                if "is_ambiguous" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN is_ambiguous INTEGER")
            except Exception as mig_err:
                logger.debug(f"Documents schema migration note: {mig_err}")

            # 4. Processed batches table migrations
            try:
                res = conn.exec_driver_sql("PRAGMA table_info(processed_batches)")
                existing_cols = [row[1] for row in res.fetchall()]
                if "original_filename" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE processed_batches ADD COLUMN original_filename VARCHAR(255) DEFAULT 'document.pdf'")
            except Exception as mig_err:
                logger.debug(f"Processed Batches schema migration note: {mig_err}")

            conn.commit()

        logger.info("Relational database schema initialized successfully via SQLAlchemy Base metadata.")
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        raise e


def seed_initial_data(configs_dir: str = "configs"):
    """
    Seeds statuses, discoverable sources, and default API credentials using SQLAlchemy ORM.
    """
    try:
        with get_db_session() as session:
            # 1. Seed document statuses
            statuses = [
                ("PENDING", "Pending Review", "Document is waiting for initial preprocessing or splitting."),
                ("PREPROCESSED", "Preprocessed", "Document is split and matched, ready for AI extraction."),
                ("EXTRACTED", "Extracted", "AI successfully extracted document payload to JSON file, waiting for DB insertion."),
                ("NEEDS_REVIEW", "Needs Review", "Document requires manual review before approval."),
                ("PROCESSED", "Processed", "AI successfully extracted document payload, waiting for human audit."),
                ("APPROVED", "Approved", "Document has been approved by the user and locked."),
                ("REJECTED", "Rejected", "Document has been rejected by the user."),
                ("COMPLETED", "Completed", "Document payload has been exported to CSV and archived."),
                ("FAILED", "Failed", "Document processing failed due to technical error or missing scans.")
            ]
            for code, name, desc_text in statuses:
                status_obj = session.query(DocumentStatus).filter_by(status_code=code).first()
                if not status_obj:
                    session.add(DocumentStatus(status_code=code, display_name=name, description=desc_text))

            # 2. Discover and seed document sources
            abs_configs_dir = PROJECT_ROOT / configs_dir if not os.path.isabs(configs_dir) else Path(configs_dir)
            doc_types_dir = str(abs_configs_dir / "doc_types")
            if not os.path.exists(doc_types_dir):
                doc_types_dir = str(abs_configs_dir / "domains")

            if os.path.exists(doc_types_dir):
                for dt_id in os.listdir(doc_types_dir):
                    dt_path = os.path.join(doc_types_dir, dt_id)
                    if os.path.isdir(dt_path) and not dt_id.startswith("."):
                        def_src = session.query(DocumentSource).filter_by(source_id="_default", domain_id=dt_id).first()
                        if not def_src:
                            session.add(DocumentSource(source_id="_default", domain_id=dt_id, display_name="Default Fallback", is_active=1))

                        sources_dir = os.path.join(dt_path, "sources")
                        if os.path.exists(sources_dir):
                            for entry in os.listdir(sources_dir):
                                entry_path = os.path.join(sources_dir, entry)
                                if os.path.isdir(entry_path) and not entry.startswith("_"):
                                    display_name = entry.replace("_", " ").title()
                                    s_obj = session.query(DocumentSource).filter_by(source_id=entry, domain_id=dt_id).first()
                                    if not s_obj:
                                        session.add(DocumentSource(source_id=entry, domain_id=dt_id, display_name=display_name, is_active=1))
            else:
                for fallback_dt in ["expense_receipt", "tax_invoice", "withholding_tax"]:
                    def_src = session.query(DocumentSource).filter_by(source_id="_default", domain_id=fallback_dt).first()
                    if not def_src:
                        session.add(DocumentSource(source_id="_default", domain_id=fallback_dt, display_name="Default Fallback", is_active=1))

            # 3. Seed default API credentials
            cred_obj = session.query(ApiCredential).filter_by(credential_id="cred_gemini_default").first()
            if not cred_obj:
                session.add(ApiCredential(
                    credential_id="cred_gemini_default",
                    provider="gemini",
                    model_name="gemini-3.5-flash",
                    api_key_env="GEMINI_API_KEY",
                    is_active=1,
                    last_active_at=None,
                    error_count=0
                ))

        logger.info("Database seeding completed.")
    except Exception as e:
        logger.error(f"Failed to seed database: {e}")


def reset_pipeline_database(clear_documents_only: bool = True) -> dict:
    """
    Safely resets pipeline database tables using SQLAlchemy ORM.
    """
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
                count = session.query(model_cls).delete()
                deleted_counts[tbl_name] = count

        return {"status": "SUCCESS", "cleared_tables": deleted_counts}
    except Exception as e:
        logger.error(f"Failed to reset pipeline database: {e}")
        return {"status": "ERROR", "error": str(e)}
