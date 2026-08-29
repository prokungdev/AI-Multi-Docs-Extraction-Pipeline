"""Unit tests for Enterprise RBAC, Multi-Company Mapping, Super Admin Bypass, and 7 Edge Cases.

Uses Isolated SQLite in-memory / temp database via conftest.
"""

import pytest
from sqlalchemy import select
from src.infrastructure.core.constants import SystemUserId, UserRole
from src.infrastructure.database import (
    initialize_db_schema,
    get_db_session,
    create_user,
    update_user,
    assign_user_to_company,
    remove_user_from_company,
    get_user_companies,
    has_company_access,
    get_accessible_companies,
    get_default_company_for_user,
    list_roles,
    get_user_by_id,
    get_user_by_email,
    list_users,
    create_company,
    seed_initial_data,
    User,
    Role,
    Company,
    UserCompany,
)


@pytest.fixture(autouse=True)
def setup_rbac_test_db():
    """Reset and seed base data before each test."""
    initialize_db_schema(drop_and_recreate=True)
    seed_initial_data()
    yield


def test_seed_initial_master_data():
    """Validates that all 6 master tables are seeded with expected initial records."""
    # 1. Master roles
    roles = list_roles()
    role_codes = {r["role_code"] for r in roles}
    assert {"ADMIN", "SYSTEM", "REVIEWER", "VIEWER"}.issubset(role_codes)

    admin_role = next(r for r in roles if r["role_code"] == "ADMIN")
    assert admin_role["is_admin"] == 1
    assert admin_role["is_system"] == 1

    reviewer_role = next(r for r in roles if r["role_code"] == "REVIEWER")
    assert reviewer_role["is_admin"] == 0

    # 2. Default users
    admin_usr = get_user_by_id(SystemUserId.SYSTEM_ADMIN)
    assert admin_usr is not None
    assert admin_usr["role"] == UserRole.ADMIN.value
    assert admin_usr["created_by"] == SystemUserId.SYSTEM_ADMIN
    assert admin_usr["updated_at"] is None  # Clean State Pattern
    assert admin_usr["updated_by"] is None

    demo_usr = get_user_by_id(SystemUserId.DEMO)
    assert demo_usr is not None
    assert demo_usr["role"] == UserRole.REVIEWER.value

    # 3. User Companies mapping
    demo_companies = get_user_companies(SystemUserId.DEMO)
    assert len(demo_companies) >= 1
    assert demo_companies[0]["is_default"] == 1


def test_has_company_access_super_admin_bypass():
    """👑 Super Admin (is_admin=1) bypasses company mapping and accesses all companies."""
    # Create a secondary test company with unique tax_id
    comp2 = create_company(
        company_code="C99999_TEST_BYPASS",
        company_name="Bypass Test Corp",
        created_by=SystemUserId.SYSTEM_ADMIN,
        short_name="BYPASS",
        tax_id="0105566000001"
    )
    comp2_id = comp2["company_id"]

    # Admin is NOT mapped in user_companies for comp2, but access must be GRANTED
    assert has_company_access(SystemUserId.SYSTEM_ADMIN, comp2_id) is True
    assert has_company_access(SystemUserId.AUTO_SYSTEM, comp2_id) is True

    # Admin accessible companies includes all active companies
    admin_companies = get_accessible_companies(SystemUserId.SYSTEM_ADMIN)
    admin_comp_ids = {c["company_id"] for c in admin_companies}
    assert comp2_id in admin_comp_ids


def test_has_company_access_reviewer_scoped():
    """👤 Reviewer (is_admin=0) is strictly restricted to mapped companies."""
    # Create a secondary test company with unique tax_id
    comp_unmapped = create_company(
        company_code="C88888_UNMAPPED",
        company_name="Unmapped Corp",
        created_by=SystemUserId.SYSTEM_ADMIN,
        short_name="UNMAPPED",
        tax_id="0105566000002"
    )
    unmapped_id = comp_unmapped["company_id"]

    # Demo reviewer should NOT have access to unmapped company
    assert has_company_access(SystemUserId.DEMO, unmapped_id) is False

    # Assign demo reviewer to unmapped company
    assign_user_to_company(SystemUserId.DEMO, unmapped_id, created_by=SystemUserId.SYSTEM_ADMIN, is_default=False)

    # Now demo reviewer MUST have access
    assert has_company_access(SystemUserId.DEMO, unmapped_id) is True

    # Remove mapping
    remove_user_from_company(SystemUserId.DEMO, unmapped_id)
    assert has_company_access(SystemUserId.DEMO, unmapped_id) is False


def test_edge_case_e1_inactive_user_rejected():
    """🛡️ Edge Case E1: Inactive user (is_active=0) is rejected immediately, even if Admin."""
    # Create an inactive admin
    inactive_admin = create_user(
        email="inactive_admin@test.local",
        full_name="Inactive Administrator",
        created_by=SystemUserId.SYSTEM_ADMIN,
        role=UserRole.ADMIN.value
    )
    update_user(inactive_admin["user_id"], updated_by=SystemUserId.SYSTEM_ADMIN, is_active=0)

    # Fetch default sandbox company
    demo_usr = get_user_by_id(SystemUserId.DEMO)
    comp_id = get_user_companies(demo_usr["user_id"])[0]["company_id"]

    # Inactive admin must be BLOCKED
    assert has_company_access(inactive_admin["user_id"], comp_id) is False
    assert get_accessible_companies(inactive_admin["user_id"]) == []
    assert get_default_company_for_user(inactive_admin["user_id"]) is None


def test_edge_case_e2_inactive_company_rejected():
    """🛡️ Edge Case E2: Inactive company (is_active=0) is rejected from access and listings."""
    # Create an inactive company with unique tax_id
    inactive_comp = create_company(
        company_code="C77777_INACTIVE",
        company_name="Inactive Suspended Corp",
        created_by=SystemUserId.SYSTEM_ADMIN,
        short_name="SUSPENDED",
        tax_id="0105566000003"
    )
    cid = inactive_comp["company_id"]
    with get_db_session() as session:
        comp_model = session.scalars(select(Company).filter_by(company_id=cid)).first()
        comp_model.is_active = 0

    # Even admin cannot access inactive company in normal mode
    assert has_company_access(SystemUserId.SYSTEM_ADMIN, cid) is False

    # Accessible companies does not include inactive unless specified
    accessible = get_accessible_companies(SystemUserId.SYSTEM_ADMIN, include_inactive=False)
    assert cid not in [c["company_id"] for c in accessible]

    accessible_all = get_accessible_companies(SystemUserId.SYSTEM_ADMIN, include_inactive=True)
    assert cid in [c["company_id"] for c in accessible_all]


def test_edge_case_e3_single_default_rule_and_fallback():
    """🛡️ Edge Case E3: Single default company enforcement and automatic fallbacks."""
    # Create a new reviewer
    user = create_user(
        email="multi_comp_user@test.local",
        full_name="Multi Company User",
        created_by=SystemUserId.SYSTEM_ADMIN,
        role=UserRole.REVIEWER.value
    )
    uid = user["user_id"]

    c1 = create_company(company_code="C11111_TEST", company_name="Comp 1", created_by=SystemUserId.SYSTEM_ADMIN, short_name="C1", tax_id="0105566000004")
    c2 = create_company(company_code="C22222_TEST", company_name="Comp 2", created_by=SystemUserId.SYSTEM_ADMIN, short_name="C2", tax_id="0105566000005")

    # Assign c1 with is_default=True
    assign_user_to_company(uid, c1["company_id"], created_by=SystemUserId.SYSTEM_ADMIN, is_default=True)
    def_comp = get_default_company_for_user(uid)
    assert def_comp["company_id"] == c1["company_id"]

    # Assign c2 with is_default=True -> c1 default must be reset to 0
    assign_user_to_company(uid, c2["company_id"], created_by=SystemUserId.SYSTEM_ADMIN, is_default=True)
    mappings = get_user_companies(uid)
    m1 = next(m for m in mappings if m["company_id"] == c1["company_id"])
    m2 = next(m for m in mappings if m["company_id"] == c2["company_id"])
    assert m1["is_default"] == 0
    assert m2["is_default"] == 1

    def_comp2 = get_default_company_for_user(uid)
    assert def_comp2["company_id"] == c2["company_id"]


def test_edge_case_e4_audit_stamping_on_update():
    """🛡️ Edge Case E4: Clean state on insert, proper stamping on update."""
    user = create_user(
        email="audit_user@test.local",
        full_name="Audit Track User",
        created_by="usr_system_admin",
        role=UserRole.VIEWER.value
    )
    assert user["created_by"] == "usr_system_admin"
    assert user["updated_at"] is None
    assert user["updated_by"] is None

    # Update user
    updated = update_user(user["user_id"], full_name="Audit Track User (Renamed)", updated_by="usr_system_admin")
    assert updated["full_name"] == "Audit Track User (Renamed)"
    assert updated["updated_at"] is not None
    assert updated["updated_by"] == "usr_system_admin"


def test_edge_case_e5_duplicate_mapping_prevention():
    """🛡️ Edge Case E5: Duplicate company assignment updates existing instead of error."""
    c = create_company(company_code="C33333_TEST", company_name="Comp 3", created_by=SystemUserId.SYSTEM_ADMIN, short_name="C3", tax_id="0105566000006")
    uid = SystemUserId.DEMO
    cid = c["company_id"]

    # Assign once
    m1 = assign_user_to_company(uid, cid, created_by=SystemUserId.SYSTEM_ADMIN, is_default=False)
    # Assign again (idempotent)
    m2 = assign_user_to_company(uid, cid, created_by=SystemUserId.SYSTEM_ADMIN, is_default=True)

    mappings = [m for m in get_user_companies(uid) if m["company_id"] == cid]
    assert len(mappings) == 1
    assert mappings[0]["is_default"] == 1
