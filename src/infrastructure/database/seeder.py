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
    VatType,
    TargetSystemId,
    ConsolidateModeCode,
    VoucherStatusCode,
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
    IntegrationMethod,
    TargetSystem,
    VoucherStatus,
    ConsolidateMode,
    ExpenseType,
    ExpenseAccountMapping,
    JournalVoucher,
    JournalVoucherItem,
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
        (DocumentStatusCode.PENDING.value, "Pending Review", "DocumentControl is waiting for initial preprocessing or splitting."),
        (DocumentStatusCode.PREPROCESSED.value, "Preprocessed", "DocumentControl is split and matched, ready for AI extraction."),
        (DocumentStatusCode.EXTRACTED.value, "Extracted", "AI successfully extracted document payload to JSON file, waiting for DB insertion."),
        (DocumentStatusCode.NEEDS_REVIEW.value, "Needs Review", "DocumentControl requires manual review before approval."),
        (DocumentStatusCode.PROCESSED.value, "Processed", "AI successfully extracted document payload, waiting for human audit."),
        (DocumentStatusCode.CONFIRMED.value, "Confirmed", "DocumentControl confirmed by reviewer and ready for journal voucher generation."),
        (DocumentStatusCode.APPROVED.value, "Approved", "DocumentControl payload approved and verified for financial export."),
        (DocumentStatusCode.FAILED.value, "Failed", "Extraction or validation failed completely."),
        (DocumentStatusCode.IGNORED.value, "Ignored", "DocumentControl merchant is marked as ignored and skipped from processing."),
        ("EXPORTED", "Exported", "DocumentControl is exported to destination systems.")
    ]
    for code, name, desc_text in statuses:
        status_obj = session.scalars(select(DocumentStatus).filter_by(status_code=code)).first()
        if not status_obj:
            session.add(DocumentStatus(status_code=code, display_name=name, description=desc_text))


def seed_integration_methods(session) -> None:
    """Seeds standardized integration connectivity methods."""
    methods_data = [
        ("RPA_UIPATH", "UiPath RPA Automation", "เชื่อมต่อด้วยการให้บอท UiPath ดึง JSON ไปหยอดลงหน้าจอ"),
        ("REST_API", "RESTful API Service", "เชื่อมต่อผ่าน REST Web API ตรงกับระบบปลายทาง"),
        ("WEBHOOK", "Custom Webhook Push", "ส่งออกข้อมูลแบบ Real-time Webhook เมื่อเอกสารได้รับการอนุมัติ"),
        ("CSV_EXPORT", "CSV File Export", "ส่งออกข้อมูลรูปแบบไฟล์ CSV มาตรฐาน"),
        ("EXCEL_EXPORT", "Excel File Export", "ส่งออกข้อมูลรูปแบบไฟล์ Excel สำหรับงานบัญชีทั่วไป"),
        ("DIRECT_DB", "Direct Database Integration", "เชื่อมต่อเขียนข้อมูลลงฐานข้อมูลปลายทางโดยตรง"),
    ]
    for m_id, m_name, m_desc in methods_data:
        existing = session.scalars(select(IntegrationMethod).filter_by(method_id=m_id)).first()
        if not existing:
            session.add(IntegrationMethod(
                method_id=m_id,
                method_name=m_name,
                description=m_desc,
                is_active=1,
                created_by=SystemUserId.SYSTEM_ADMIN
            ))


def seed_target_systems(session) -> None:
    """Seeds external ERP and target accounting systems."""
    systems_data = [
        (TargetSystemId.EXPRESS.value, "Express Accounting", "ACCOUNTING_ERP", "RPA_UIPATH", "บันทึกค่าใช้จ่ายผ่าน UiPath Bot เข้าหน้าจอ OE"),
        (TargetSystemId.SAP.value, "SAP ERP", "ACCOUNTING_ERP", "REST_API", "เชื่อมต่อบันทึกบัญชีเข้า SAP B1 / S4 HANA"),
        (TargetSystemId.PEAK.value, "PEAK Engine", "ACCOUNTING_ERP", "REST_API", "เชื่อมต่อระบบบัญชีคลาวด์ PEAK"),
        (TargetSystemId.HR_PORTAL.value, "HR Reimbursement Portal", "HR_REIMBURSEMENT", "REST_API", "ระบบเบิกจ่ายค่าใช้จ่ายพนักงานและสวัสดิการ"),
        (TargetSystemId.GENERIC_CSV.value, "Generic CSV Exporter", "ACCOUNTING_ERP", "CSV_EXPORT", "ส่งออกไฟล์ CSV กลางสำหรับนำเข้าโปรแกรมบัญชี"),
    ]
    for s_id, s_name, s_cat, s_method, s_desc in systems_data:
        existing = session.scalars(select(TargetSystem).filter_by(system_id=s_id)).first()
        if not existing:
            session.add(TargetSystem(
                system_id=s_id,
                system_name=s_name,
                system_category=s_cat,
                integration_method_id=s_method,
                description=s_desc,
                is_active=1,
                created_by=SystemUserId.SYSTEM_ADMIN
            ))


def seed_voucher_statuses(session) -> None:
    """Seeds standard journal voucher lifecycle and RPA processing status codes."""
    statuses = [
        (VoucherStatusCode.DRAFT.value, "แบบร่าง", "สร้าง Voucher แล้ว อยู่ระหว่างเตรียมข้อมูล"),
        (VoucherStatusCode.READY.value, "พร้อมส่งออก", "ข้อมูลครบถ้วน พร้อมให้ UiPath Bot / RPA มาดึงไปทำ"),
        (VoucherStatusCode.POSING.value, "กำลังบันทึก", "บอทกำลังดึงไปคีย์ลง Express (ติด Concurrency Lease Lock)"),
        (VoucherStatusCode.POSTED.value, "บันทึกสำเร็จ", "บันทึกเข้า Express เรียบร้อยแล้ว (ได้เลขที่สมบูรณ์)"),
        (VoucherStatusCode.ERROR.value, "เกิดข้อผิดพลาด", "บอทคีย์ไม่ผ่าน (มี Error Message ระบุสาเหตุ)"),
        (VoucherStatusCode.CANCELLED.value, "ยกเลิก", "เอกสารถูกยกเลิก ไม่นำไปประมวลผล"),
    ]
    for code, name, desc_text in statuses:
        status_obj = session.scalars(select(VoucherStatus).filter_by(status_code=code)).first()
        if not status_obj:
            session.add(VoucherStatus(status_code=code, display_name=name, description=desc_text, is_active=1))


def seed_consolidate_modes(session) -> None:
    """Seeds document consolidation modes."""
    modes = [
        (ConsolidateModeCode.BY_MERCHANT.value, "ยุบรวมทั้งบิลตามร้านค้า (Single Summary Line)", "รวมยอดทั้งบิลเป็น 1 แถวค่าใช้จ่ายในหน้า OE", 1),
        (ConsolidateModeCode.BY_CATEGORY.value, "ยุบรวมตามหมวดหมู่ค่าใช้จ่าย", "รวมยอดตามหมวดหมู่ค่าใช้จ่ายในบิล", 0),
        (ConsolidateModeCode.NO_CONSOLIDATION.value, "ไม่ยุบรวม (ลงรายการแยกตามสินค้าทุกชิ้น)", "ลงรายการบัญชีตามสินค้าทุกชิ้นในบิล", 0),
    ]
    for code, name, desc_text, is_def in modes:
        mode_obj = session.scalars(select(ConsolidateMode).filter_by(mode_code=code)).first()
        if not mode_obj:
            session.add(ConsolidateMode(
                mode_code=code,
                mode_name=name,
                description=desc_text,
                is_default=is_def,
                is_active=1,
                created_by=SystemUserId.SYSTEM_ADMIN
            ))


def seed_expense_types(session) -> None:
    """Seeds master expense types with default WHT rates."""
    types_data = [
        ("ext_service", "ค่าบริการ", 3.0, "ค่าบริการ/ค่าจ้างทำของ"),
        ("ext_transport", "ค่าขนส่ง", 1.0, "ค่าขนส่งสินค้า"),
        ("ext_fuel", "ค่าน้ำมันเชื้อเพลิง", 0.0, None),
        ("ext_misc", "ค่าใช้จ่ายเบ็ดเตล็ด", 0.0, None),
    ]
    for t_id, t_name, wht_rate, wht_income in types_data:
        existing = session.scalars(select(ExpenseType).filter_by(expense_type_id=t_id)).first()
        if not existing:
            session.add(ExpenseType(
                expense_type_id=t_id,
                expense_type_name=t_name,
                default_wht_rate=wht_rate,
                wht_income_type=wht_income,
                is_active=1,
                created_by=SystemUserId.SYSTEM_ADMIN
            ))


def seed_expense_account_mappings(session, company_id: str) -> None:
    """Seeds default GL account mappings for Express OE."""
    mappings = [
        ("EXPRESS", "ค่าบริการ", "95-5310-19", "ค่าบริการและที่ปรึกษา"),
        ("EXPRESS", "ค่าขนส่ง", "95-5200-05", "ค่าขนส่งสินค้า"),
    ]
    for tgt_sys, exp_type, acc_code, acc_name in mappings:
        stmt = select(ExpenseAccountMapping).filter_by(
            company_id=company_id,
            target_system_id=tgt_sys,
            expense_type_name=exp_type
        )
        existing = session.scalars(stmt).first()
        if not existing:
            session.add(ExpenseAccountMapping(
                mapping_id=generate_entity_id(EntityIdPrefix.EXPENSE_ACCOUNT_MAPPING),
                company_id=company_id,
                target_system_id=tgt_sys,
                expense_type_name=exp_type,
                account_code=acc_code,
                account_name=acc_name,
                department_code="",
                created_by=SystemUserId.SYSTEM_ADMIN
            ))


def seed_default_merchants(session, company_id: str) -> None:
    """Seeds default generic and real-world test merchants (Grab, SPX, Shopee)."""
    # 1. Generic Cash Slip / No Tax ID
    def_merch = session.scalars(select(Merchant).filter_by(merchant_id=DefaultIdentifier.NO_TAX_ID)).first()
    if not def_merch:
        session.add(Merchant(
            merchant_id=DefaultIdentifier.NO_TAX_ID,
            company_id=company_id,
            tax_id="0000000000000",
            merchant_name="No Tax ID / Cash Slip",
            short_name="no_taxid",
            file_prefix="cash_slip",
            vendor_code="MISC",
            default_expense_type="ค่าใช้จ่ายเบ็ดเตล็ด",
            consolidate_mode=ConsolidateModeCode.BY_MERCHANT.value,
            default_vat_type=VatType.NO_VAT.value,
            has_wht=0,
            default_wht_rate=0.0,
            status_code=MerchantStatus.APPROVED.value,
            is_vat_registered=0,
            is_override_vat=1,
            created_by=SystemUserId.SYSTEM_ADMIN
        ))

    # 2. Real-World Express Test Merchants
    real_merchants = [
        {
            "merchant_id": "merch_grab_thailand",
            "tax_id": "0105556090377",
            "merchant_name": "Grabtaxi (Thailand) Co., Ltd.",
            "short_name": "grab",
            "file_prefix": "grab",
            "vendor_code": "G0001",
            "default_expense_type": "ค่าบริการ",
            "consolidate_mode": ConsolidateModeCode.BY_MERCHANT.value,
            "default_vat_type": VatType.EXCLUSIVE.value,
            "has_wht": 1,
            "default_wht_rate": 3.0,
            "is_vat_registered": 1,
            "is_override_vat": 1,
        },
        {
            "merchant_id": "merch_spx_express",
            "tax_id": "0105562002073",
            "merchant_name": "SPX Express (Thailand) Co., Ltd.",
            "short_name": "spx",
            "file_prefix": "spx",
            "vendor_code": "อ0022",
            "default_expense_type": "ค่าขนส่ง",
            "consolidate_mode": ConsolidateModeCode.BY_MERCHANT.value,
            "default_vat_type": VatType.NO_VAT.value,
            "has_wht": 0,
            "default_wht_rate": 0.0,
            "is_vat_registered": 0,
            "is_override_vat": 1,
        },
        {
            "merchant_id": "merch_shopee_thailand",
            "tax_id": "0105558021119",
            "merchant_name": "Shopee (Thailand) Co., Ltd.",
            "short_name": "shopee",
            "file_prefix": "shopee",
            "vendor_code": "S0002",
            "default_expense_type": "ค่าบริการ",
            "consolidate_mode": ConsolidateModeCode.BY_MERCHANT.value,
            "default_vat_type": VatType.INCLUSIVE.value,
            "has_wht": 0,
            "default_wht_rate": 0.0,
            "is_vat_registered": 1,
            "is_override_vat": 1,
        },
    ]
    for m in real_merchants:
        existing = session.scalars(select(Merchant).filter_by(merchant_id=m["merchant_id"])).first()
        if not existing:
            session.add(Merchant(
                company_id=company_id,
                status_code=MerchantStatus.APPROVED.value,
                created_by=SystemUserId.SYSTEM_ADMIN,
                **m
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
    """Main entry point for database master data and reference seed population across all tables."""
    try:
        with get_db_session() as session:
            seed_roles(session)
            seed_ai_model_configs(session)
            seed_document_types(session)
            seed_integration_methods(session)
            seed_target_systems(session)
            seed_voucher_statuses(session)
            seed_consolidate_modes(session)
            seed_expense_types(session)
            company = seed_default_company(session)
            seed_expense_account_mappings(session, company_id=company.company_id)
            seed_document_statuses(session)
            seed_default_merchants(session, company_id=company.company_id)
            seed_default_users(session, company_id=company.company_id)

        logger.info("Database master data seeding completed successfully across all tables.")
    except Exception as e:
        logger.error(f"Failed to seed database: {e}")
        raise e

