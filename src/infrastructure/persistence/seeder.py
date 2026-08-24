"""
Database Initial Seeder & Data Master Population.
Provides Pure SQLAlchemy 2.0 ORM routines for seeding default tenant, statuses, doc sources, and default users.
"""

import os
from pathlib import Path
from sqlalchemy import select, update
from src.infrastructure.common.logger import logger
from src.infrastructure.common.constants import (
    DefaultCompany,
    DefaultIdentifier,
    EntityIdPrefix,
    DocumentStatusCode,
    SystemUserId,
    UserRole,
    generate_entity_id,
)
from .connection import get_db_session
from .models import (
    Company,
    DocumentStatus,
    User,
    ProcessedBatch,
    Document,
    Merchant,
    MerchantStatus,
    ExpenseReceipt,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def seed_default_company(session) -> Company:
    """Ensures default sandbox company exists and backfills orphaned records."""
    stmt = select(Company).filter_by(company_code=DefaultCompany.CODE)
    default_company = session.scalars(stmt).first()
    if not default_company:
        default_company = Company(
            company_id=generate_entity_id(EntityIdPrefix.COMPANY),
            company_code=DefaultCompany.CODE,
            company_name=DefaultCompany.NAME,
            short_name=DefaultCompany.SHORT_NAME,
            tax_id=DefaultCompany.TAX_ID,
            branch_code=DefaultCompany.BRANCH_CODE,
            is_active=1
        )
        session.add(default_company)
        session.flush()

    # Backfill legacy records without company_id
    default_cid = default_company.company_id
    session.execute(update(ProcessedBatch).where(ProcessedBatch.company_id.is_(None)).values(company_id=default_cid))
    session.execute(update(Document).where(Document.company_id.is_(None)).values(company_id=default_cid))
    session.execute(update(Merchant).where(Merchant.company_id.is_(None)).values(company_id=default_cid))
    session.execute(update(ExpenseReceipt).where(ExpenseReceipt.company_id.is_(None)).values(company_id=default_cid))

    return default_company


def seed_document_statuses(session) -> None:
    """Seeds standard document lifecycle status codes."""
    statuses = [
        (DocumentStatusCode.PENDING, "Pending Review", "Document is waiting for initial preprocessing or splitting."),
        (DocumentStatusCode.PREPROCESSED, "Preprocessed", "Document is split and matched, ready for AI extraction."),
        (DocumentStatusCode.EXTRACTED, "Extracted", "AI successfully extracted document payload to JSON file, waiting for DB insertion."),
        (DocumentStatusCode.NEEDS_REVIEW, "Needs Review", "Document requires manual review before approval."),
        (DocumentStatusCode.PROCESSED, "Processed", "AI successfully extracted document payload, waiting for human audit."),
        (DocumentStatusCode.APPROVED, "Approved", "Document payload approved and verified for financial export."),
        (DocumentStatusCode.FAILED, "Failed", "Extraction or validation failed completely."),
        (DocumentStatusCode.IGNORED, "Ignored", "Document merchant is marked as ignored and skipped from processing."),
        ("EXPORTED", "Exported", "Document is exported to destination systems.")
    ]
    for code, name, desc_text in statuses:
        status_obj = session.scalars(select(DocumentStatus).filter_by(status_code=code)).first()
        if not status_obj:
            session.add(DocumentStatus(status_code=code, display_name=name, description=desc_text))


def seed_default_merchants(session, company_id: str) -> None:
    """Seeds default generic merchant for cash slips / unclassified receipts."""
    def_merch = session.scalars(select(Merchant).filter_by(merchant_id=DefaultIdentifier.NO_TAX_ID)).first()
    if not def_merch:
        session.add(Merchant(
            merchant_id=DefaultIdentifier.NO_TAX_ID,
            company_id=company_id,
            tax_id="0000000000000",
            merchant_name="No Tax ID / Cash Slip",
            short_name="no_taxid",
            file_prefix="cash_slip",
            status_code=MerchantStatus.APPROVED.value,
            is_vat_registered=0,
            default_wht_rate=0.0
        ))


def seed_default_users(session, company_id: str) -> None:
    """Seeds default system actor and development administrator accounts."""
    sys_user = session.scalars(select(User).filter_by(user_id=SystemUserId.AUTO_SYSTEM)).first()
    if not sys_user:
        session.add(User(
            user_id=SystemUserId.AUTO_SYSTEM,
            company_id=company_id,
            email="system@pipeline.local",
            full_name="Auto Pipeline System",
            role=UserRole.SYSTEM.value,
            is_active=1
        ))

    dev_admin = session.scalars(select(User).filter_by(user_id=SystemUserId.DEV_ADMIN)).first()
    if not dev_admin:
        session.add(User(
            user_id=SystemUserId.DEV_ADMIN,
            company_id=company_id,
            email="admin@dev.local",
            full_name="Development Administrator",
            role=UserRole.ADMIN.value,
            is_active=1
        ))


def seed_initial_data(configs_dir: str = "configs") -> None:
    """
    Main entry point for database master data and reference seed population.
    """
    try:
        with get_db_session() as session:
            company = seed_default_company(session)
            seed_document_statuses(session)
            seed_default_merchants(session, company_id=company.company_id)
            seed_default_users(session, company_id=company.company_id)

        logger.info("Database seeding completed.")
    except Exception as e:
        logger.error(f"Failed to seed database: {e}")
