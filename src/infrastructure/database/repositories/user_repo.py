"""User RBAC entity repository using Pure SQLAlchemy 2.0 ORM.

Provides Enterprise RBAC, Multi-Company Mapping, Data-Driven Super Admin Bypass, and Audit Trails.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import (
    DefaultCompany,
    EntityIdPrefix,
    SystemUserId,
    UserRole,
    generate_entity_id,
)
from ..engine import get_db_session
from ..models import User, Role, UserCompany, Company


def create_user(
    email: str,
    full_name: str,
    created_by: str,
    role: str = UserRole.REVIEWER.value,
    password_hash: Optional[str] = None,
    user_id: Optional[str] = None
) -> dict:
    """Creates a new user entity in the database with fail-fast validation and Audit Trail. Requires created_by."""
    clean_email = email.strip().lower()
    clean_name = full_name.strip()
    clean_role = role.strip().upper() if role else UserRole.REVIEWER.value
    uid = user_id or generate_entity_id(EntityIdPrefix.USER)
    now_str = datetime.now(timezone.utc).isoformat()

    try:
        with get_db_session() as session:
            # 1. Validate email uniqueness
            stmt = select(User).filter_by(email=clean_email)
            existing = session.scalars(stmt).first()
            if existing:
                error_msg = f"User with email '{clean_email}' already exists."
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 2. Validate Role existence
            role_obj = session.scalars(select(Role).filter_by(role_code=clean_role)).first()
            if not role_obj:
                error_msg = f"Invalid role '{clean_role}'. Role does not exist in master roles."
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 3. Create User with Clean State Audit Fields
            new_user = User(
                user_id=uid,
                email=clean_email,
                full_name=clean_name,
                password_hash=password_hash,
                role=clean_role,
                is_active=1,
                created_at=now_str,
                created_by=created_by,
                updated_at=None,
                updated_by=None
            )
            session.add(new_user)
            session.flush()
            logger.info(f"Created user '{clean_email}' with ID '{uid}' (Role: {clean_role}) by '{created_by}'.")
            return new_user.to_dict()
    except Exception as e:
        logger.error(f"Failed to create user '{clean_email}': {e}")
        raise


def update_user(
    user_id: str,
    updated_by: str,
    full_name: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[int] = None,
    password_hash: Optional[str] = None
) -> Optional[dict]:
    """Updates an existing user entity and stamps updated_at and updated_by. Requires updated_by."""
    now_str = datetime.now(timezone.utc).isoformat()
    try:
        with get_db_session() as session:
            stmt = select(User).filter_by(user_id=user_id.strip())
            user = session.scalars(stmt).first()
            if not user:
                return None

            if full_name is not None:
                user.full_name = full_name.strip()
            if role is not None:
                clean_role = role.strip().upper()
                role_obj = session.scalars(select(Role).filter_by(role_code=clean_role)).first()
                if not role_obj:
                    raise ValueError(f"Invalid role '{clean_role}'. Role does not exist.")
                user.role = clean_role
            if is_active is not None:
                user.is_active = int(is_active)
            if password_hash is not None:
                user.password_hash = password_hash

            user.updated_at = now_str
            user.updated_by = updated_by
            session.flush()
            return user.to_dict()
    except Exception as e:
        logger.error(f"Failed to update user '{user_id}': {e}")
        raise


def assign_user_to_company(
    user_id: str,
    company_id: str,
    created_by: str,
    is_default: bool = False
) -> dict:
    """Assigns a user to a company with Single-Default Rule enforcement. Requires created_by."""
    uid = user_id.strip()
    cid = company_id.strip()
    now_str = datetime.now(timezone.utc).isoformat()

    try:
        with get_db_session() as session:
            # 1. Verify user & company exist
            user = session.scalars(select(User).filter_by(user_id=uid)).first()
            if not user:
                raise ValueError(f"User '{uid}' not found.")
            company = session.scalars(select(Company).filter_by(company_id=cid)).first()
            if not company:
                raise ValueError(f"Company '{cid}' not found.")

            # 2. Enforce Single-Default Rule (if setting is_default=1, unset others)
            if is_default:
                session.execute(
                    update(UserCompany).where(UserCompany.user_id == uid).values(is_default=0)
                )

            # 3. Insert or update mapping
            existing_mapping = session.scalars(
                select(UserCompany).filter_by(user_id=uid, company_id=cid)
            ).first()

            if existing_mapping:
                existing_mapping.is_default = 1 if is_default else existing_mapping.is_default
                session.flush()
                return existing_mapping.to_dict()

            new_mapping = UserCompany(
                id=generate_entity_id(EntityIdPrefix.USER_COMPANY),
                user_id=uid,
                company_id=cid,
                is_default=1 if is_default else 0,
                created_at=now_str,
                created_by=created_by
            )
            session.add(new_mapping)
            session.flush()
            logger.info(f"Assigned user '{uid}' to company '{cid}' (Default: {is_default}).")
            return new_mapping.to_dict()
    except Exception as e:
        logger.error(f"Failed to assign user '{uid}' to company '{cid}': {e}")
        raise


def remove_user_from_company(user_id: str, company_id: str) -> bool:
    """Removes a user's access mapping to a specific company."""
    try:
        with get_db_session() as session:
            stmt = select(UserCompany).filter_by(user_id=user_id.strip(), company_id=company_id.strip())
            mapping = session.scalars(stmt).first()
            if not mapping:
                return False
            session.delete(mapping)
            return True
    except Exception as e:
        logger.error(f"Failed to remove user '{user_id}' from company '{company_id}': {e}")
        return False


def get_user_companies(user_id: str) -> list[dict]:
    """Retrieves all company mappings for a given user."""
    try:
        with get_db_session() as session:
            stmt = select(UserCompany).filter_by(user_id=user_id.strip())
            mappings = session.scalars(stmt).all()
            return [m.to_dict() for m in mappings]
    except Exception as e:
        logger.error(f"Failed to get companies for user '{user_id}': {e}")
        return []


def has_company_access(user_id: str, company_id: str) -> bool:
    """Evaluates whether a user is authorized to access a given company.
    
    Guards & Defenses:
    - E1: Rejects inactive users immediately (is_active == 0)
    - E2: Rejects inactive companies immediately (is_active == 0)
    - Data-Driven Bypass: If user's Role has is_admin == 1 -> GRANTED (Bypass All)
    - Scoped Verification: Checks user_companies mapping for non-admin users
    """
    try:
        with get_db_session() as session:
            # 1. Fetch user & role
            user = session.scalars(select(User).filter_by(user_id=user_id.strip())).first()
            if not user or user.is_active != 1:
                return False  # Edge Case 1: Inactive user rejected

            # 2. Fetch company
            company = session.scalars(select(Company).filter_by(company_id=company_id.strip())).first()
            if not company or company.is_active != 1:
                return False  # Edge Case 2: Inactive company rejected

            # 3. Check Role Data-Driven Admin Bypass Flag
            role = session.scalars(select(Role).filter_by(role_code=user.role)).first()
            if role and role.is_admin == 1:
                return True  # 👑 Data-Driven Super Admin Bypass

            # 4. Scoped Tenant Mapping Check
            mapping = session.scalars(
                select(UserCompany).filter_by(user_id=user.user_id, company_id=company.company_id)
            ).first()
            return mapping is not None
    except Exception as e:
        logger.error(f"Error checking company access for user '{user_id}' and company '{company_id}': {e}")
        return False


def get_accessible_companies(user_id: str, include_inactive: bool = False) -> list[dict]:
    """Retrieves list of all companies accessible by the user."""
    try:
        with get_db_session() as session:
            user = session.scalars(select(User).filter_by(user_id=user_id.strip())).first()
            if not user or user.is_active != 1:
                return []  # Inactive user has zero access

            role = session.scalars(select(Role).filter_by(role_code=user.role)).first()
            if role and role.is_admin == 1:
                # 👑 Admin sees all companies
                stmt = select(Company)
                if not include_inactive:
                    stmt = stmt.filter_by(is_active=1)
                companies = session.scalars(stmt).all()
                return [c.to_dict() for c in companies]

            # Scoped user: query mapped companies
            stmt = select(Company).join(
                UserCompany, Company.company_id == UserCompany.company_id
            ).filter(UserCompany.user_id == user.user_id)
            if not include_inactive:
                stmt = stmt.filter(Company.is_active == 1)
            companies = session.scalars(stmt).all()
            return [c.to_dict() for c in companies]
    except Exception as e:
        logger.error(f"Failed to get accessible companies for user '{user_id}': {e}")
        return []


def get_default_company_for_user(user_id: str) -> Optional[dict]:
    """Resolves the default active company for user login session (Handling Edge Case 3)."""
    try:
        with get_db_session() as session:
            user = session.scalars(select(User).filter_by(user_id=user_id.strip())).first()
            if not user or user.is_active != 1:
                return None

            # 1. Check for explicit is_default=1 mapping
            stmt = select(Company).join(
                UserCompany, Company.company_id == UserCompany.company_id
            ).filter(UserCompany.user_id == user.user_id, UserCompany.is_default == 1, Company.is_active == 1)
            def_comp = session.scalars(stmt).first()
            if def_comp:
                return def_comp.to_dict()

            # 2. Fallback: First mapped active company
            stmt_first = select(Company).join(
                UserCompany, Company.company_id == UserCompany.company_id
            ).filter(UserCompany.user_id == user.user_id, Company.is_active == 1)
            first_mapped = session.scalars(stmt_first).first()
            if first_mapped:
                return first_mapped.to_dict()

            # 3. Fallback for Admin: System Default Sandbox Company
            role = session.scalars(select(Role).filter_by(role_code=user.role)).first()
            if role and role.is_admin == 1:
                stmt_sandbox = select(Company).filter_by(company_code=DefaultCompany.CODE, is_active=1)
                sandbox_comp = session.scalars(stmt_sandbox).first()
                if sandbox_comp:
                    return sandbox_comp.to_dict()
                # Fallback to any active company
                any_comp = session.scalars(select(Company).filter_by(is_active=1)).first()
                return any_comp.to_dict() if any_comp else None

            return None
    except Exception as e:
        logger.error(f"Failed to resolve default company for user '{user_id}': {e}")
        return None


def list_roles() -> list[dict]:
    """Retrieves all RBAC role definitions from master roles table."""
    try:
        with get_db_session() as session:
            stmt = select(Role).order_by(Role.is_admin.desc(), Role.role_code)
            roles = session.scalars(stmt).all()
            return [r.to_dict() for r in roles]
    except Exception as e:
        logger.error(f"Failed to list roles: {e}")
        return []


def get_user_by_id(user_id: str) -> Optional[dict]:
    """Retrieves a user entity dictionary by user_id."""
    try:
        with get_db_session() as session:
            stmt = select(User).filter_by(user_id=user_id.strip())
            user = session.scalars(stmt).first()
            return user.to_dict() if user else None
    except Exception as e:
        logger.error(f"Failed to get user by ID '{user_id}': {e}")
        return None


def get_user_by_email(email: str) -> Optional[dict]:
    """Retrieves a user entity dictionary by email."""
    try:
        with get_db_session() as session:
            stmt = select(User).filter_by(email=email.strip().lower())
            user = session.scalars(stmt).first()
            return user.to_dict() if user else None
    except Exception as e:
        logger.error(f"Failed to get user by email '{email}': {e}")
        return None


def list_users(role: Optional[str] = None) -> list[dict]:
    """Lists users optionally filtered by role."""
    try:
        with get_db_session() as session:
            stmt = select(User)
            if role:
                stmt = stmt.filter_by(role=role.strip().upper())
            users = session.scalars(stmt).all()
            return [u.to_dict() for u in users]
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        return []
