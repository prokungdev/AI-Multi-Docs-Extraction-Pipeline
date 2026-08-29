"""Database Initial Seeder & Master Data Population.

Provides Pure SQLAlchemy 2.0 ORM routines for seeding default roles, tenant, statuses, doc sources, and default users.
Includes Enterprise RBAC Multi-Company Mapping and Audit Trails.
"""

import os
from pathlib import Path
from sqlalchemy import select, update
from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import (
    DefaultCompany,
    DefaultIdentifier,
    EntityIdPrefix,
    DocumentStatusCode,
    SystemUserId,
    UserRole,
    generate_entity_id,
)
from .engine import get_db_session
from .models import (
    Role,
    Company,
    DocumentStatus,
    DocumentType,
    AIModelConfig,
    User,
    UserCompany,
    Batch,
    DocumentControl,
    Merchant,
    MerchantStatus,
    ExpenseReceipt,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def seed_roles(session) -> None:
    """Seeds standardized RBAC roles with Data-Driven Admin Bypass Flags."""
    roles_data = [
        (UserRole.ADMIN.value, "ผู้ดูแลระบบสูงสุด", "สิทธิ์สูงสุด สามารถเข้าถึงและจัดการได้ทุก Company ในระบบ (Bypass All Companies)", 1, 1),
        (UserRole.SYSTEM.value, "ระบบประมวลผลอัตโนมัติ", "Service Account สำหรับ Background Pipeline และ AI Worker (Bypass All Companies)", 1, 1),
        (UserRole.REVIEWER.value, "ผู้ตรวจสอบเอกสาร", "สิทธิ์ตรวจสอบ แก้ไขตัวเลข และอนุมัติเอกสารเฉพาะ Company ที่ได้รับมอบหมาย", 0, 1),
        (UserRole.VIEWER.value, "ผู้อ่านข้อมูลทั่วไป", "สิทธิ์ดูเอกสาร สรุปยอด และดาวน์โหลดรายงาน Export เฉพาะ Company ที่ได้รับมอบหมาย", 0, 1),
    ]
    for code, name, desc_text, is_adm, is_sys in roles_data:
        existing = session.scalars(select(Role).filter_by(role_code=code)).first()
        if not existing:
            session.add(Role(
                role_code=code,
                role_name=name,
                description=desc_text,
                is_admin=is_adm,
                is_system=is_sys,
                created_by=SystemUserId.SYSTEM_ADMIN
            ))


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
            is_active=1,
            created_by=SystemUserId.SYSTEM_ADMIN
        )
        session.add(default_company)
        session.flush()

    # Backfill legacy records without company_id
    default_cid = default_company.company_id
    session.execute(update(Batch).where(Batch.company_id.is_(None)).values(company_id=default_cid))
    session.execute(update(DocumentControl).where(DocumentControl.company_id.is_(None)).values(company_id=default_cid))
    session.execute(update(Merchant).where(Merchant.company_id.is_(None)).values(company_id=default_cid))
    session.execute(update(ExpenseReceipt).where(ExpenseReceipt.company_id.is_(None)).values(company_id=default_cid))

    return default_company


def seed_document_statuses(session) -> None:
    """Seeds standard document lifecycle status codes."""
    statuses = [
        (DocumentStatusCode.PENDING, "Pending Review", "DocumentControl is waiting for initial preprocessing or splitting."),
        (DocumentStatusCode.PREPROCESSED, "Preprocessed", "DocumentControl is split and matched, ready for AI extraction."),
        (DocumentStatusCode.EXTRACTED, "Extracted", "AI successfully extracted document payload to JSON file, waiting for DB insertion."),
        (DocumentStatusCode.NEEDS_REVIEW, "Needs Review", "DocumentControl requires manual review before approval."),
        (DocumentStatusCode.PROCESSED, "Processed", "AI successfully extracted document payload, waiting for human audit."),
        (DocumentStatusCode.APPROVED, "Approved", "DocumentControl payload approved and verified for financial export."),
        (DocumentStatusCode.FAILED, "Failed", "Extraction or validation failed completely."),
        (DocumentStatusCode.IGNORED, "Ignored", "DocumentControl merchant is marked as ignored and skipped from processing."),
        ("EXPORTED", "Exported", "DocumentControl is exported to destination systems.")
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
            default_wht_rate=0.0,
            created_by=SystemUserId.SYSTEM_ADMIN
        ))


def seed_default_users(session, company_id: str) -> None:
    """Seeds default system actor, admin, and demo reviewer accounts along with Multi-Company mapping."""
    # 1. System Administrator (Bypass All Companies)
    admin_user = session.scalars(select(User).filter_by(user_id=SystemUserId.SYSTEM_ADMIN)).first()
    if not admin_user:
        admin_user = User(
            user_id=SystemUserId.SYSTEM_ADMIN,
            email="admin@system.local",
            full_name="System Administrator",
            role=UserRole.ADMIN.value,
            is_active=1,
            created_by=SystemUserId.SYSTEM_ADMIN
        )
        session.add(admin_user)

    # 2. Automated Pipeline Actor (Bypass All Companies)
    sys_auto = session.scalars(select(User).filter_by(user_id=SystemUserId.AUTO_SYSTEM)).first()
    if not sys_auto:
        sys_auto = User(
            user_id=SystemUserId.AUTO_SYSTEM,
            email="system@pipeline.local",
            full_name="Auto Pipeline System",
            role=UserRole.SYSTEM.value,
            is_active=1,
            created_by=SystemUserId.SYSTEM_ADMIN
        )
        session.add(sys_auto)

    # 3. Demo Reviewer User (Scoped to Company)
    demo_user = session.scalars(select(User).filter_by(user_id=SystemUserId.DEMO)).first()
    if not demo_user:
        demo_user = User(
            user_id=SystemUserId.DEMO,
            email="demo@pipeline.local",
            full_name="Demo Reviewer User",
            role=UserRole.REVIEWER.value,
            is_active=1,
            created_by=SystemUserId.SYSTEM_ADMIN
        )
        session.add(demo_user)
        session.flush()

    # 4. System Test Runner Actor (Bypass All Companies)
    sys_test = session.scalars(select(User).filter_by(user_id=SystemUserId.SYSTEM_TEST)).first()
    if not sys_test:
        sys_test = User(
            user_id=SystemUserId.SYSTEM_TEST,
            email="test@pipeline.local",
            full_name="System Test Runner",
            role=UserRole.ADMIN.value,
            is_active=1,
            created_by=SystemUserId.SYSTEM_ADMIN
        )
        session.add(sys_test)

    # 5. Map Demo User to Default Sandbox Company in user_companies
    if demo_user and company_id:
        mapping = session.scalars(
            select(UserCompany).filter_by(user_id=demo_user.user_id, company_id=company_id)
        ).first()
        if not mapping:
            session.add(UserCompany(
                id=generate_entity_id(EntityIdPrefix.USER_COMPANY),
                user_id=demo_user.user_id,
                company_id=company_id,
                is_default=1,
                created_by=SystemUserId.SYSTEM_ADMIN
            ))


def seed_ai_model_configs(session) -> None:
    """Seeds default AI provider and model configurations with pricing and rate limits."""
    configs_data = [
        {
            "config_id": DefaultIdentifier.AI_CONFIG_FREE,
            "config_name": "Gemini 3.5 Flash Lite (Free Tier)",
            "provider": "gemini",
            "model_name": "gemini-3.5-flash-lite",
            "billing_tier": "free",
            "api_key_env_var": "api_key_env_default_free",
            "input_price_per_million": 0.0375,
            "output_price_per_million": 0.15,
            "exchange_rate_thb": 36.0,
            "max_concurrent_requests": 8,
            "is_default": 1,
            "is_active": 1,
            "created_by": SystemUserId.SYSTEM_ADMIN,
        },
        {
            "config_id": DefaultIdentifier.AI_CONFIG_PAID,
            "config_name": "Gemini 3.5 Flash (Paid Tier)",
            "provider": "gemini",
            "model_name": "gemini-3.5-flash",
            "billing_tier": "paid",
            "api_key_env_var": "api_key_env_default_paid",
            "input_price_per_million": 0.075,
            "output_price_per_million": 0.3,
            "exchange_rate_thb": 36.0,
            "max_concurrent_requests": 8,
            "is_default": 0,
            "is_active": 1,
            "created_by": SystemUserId.SYSTEM_ADMIN,
        },
    ]
    for cfg in configs_data:
        existing = session.scalars(select(AIModelConfig).filter_by(config_id=cfg["config_id"])).first()
        if not existing:
            session.add(AIModelConfig(**cfg))


def seed_document_types(session) -> None:
    """Seeds baseline document types and quality/validation thresholds from DocTypeRegistry."""
    from src.domain.doc_types import DocTypeRegistry

    for dt_strategy in DocTypeRegistry.list_all():
        dt_dict = dt_strategy.to_dict()
        doc_type_id = dt_dict["doc_type_id"]
        existing = session.scalars(select(DocumentType).filter_by(doc_type_id=doc_type_id)).first()
        if not existing:
            proc_type = dt_dict.get("processing_type")
            if hasattr(proc_type, "value"):
                proc_type = proc_type.value

            session.add(DocumentType(
                doc_type_id=doc_type_id,
                display_name=dt_dict.get("display_name") or dt_strategy.display_name,
                description=dt_dict.get("description") or getattr(dt_strategy, "description", None),
                processing_type=str(proc_type or "AI"),
                sort_order=dt_dict.get("sort_order", 1),
                is_active=dt_dict.get("is_active", 1),
                confidence_high=dt_dict.get("confidence_high"),
                confidence_review=dt_dict.get("confidence_review"),
                confidence_low=dt_dict.get("confidence_low"),
                financial_tolerance=dt_dict.get("financial_tolerance"),
                split_filename_pattern=dt_dict.get("split_filename_pattern"),
                archive_filename_pattern=dt_dict.get("archive_filename_pattern"),
                dpi=dt_dict.get("dpi", 150),
                created_by=SystemUserId.SYSTEM_ADMIN,
            ))


def seed_initial_data(configs_dir: str = "configs") -> None:
    """Main entry point for database master data and reference seed population across all 8 tables."""
    try:
        with get_db_session() as session:
            seed_roles(session)
            seed_ai_model_configs(session)
            seed_document_types(session)
            company = seed_default_company(session)
            seed_document_statuses(session)
            seed_default_merchants(session, company_id=company.company_id)
            seed_default_users(session, company_id=company.company_id)

        logger.info("Database master data seeding completed successfully across all 8 tables.")
    except Exception as e:
        logger.error(f"Failed to seed database: {e}")
        raise e

