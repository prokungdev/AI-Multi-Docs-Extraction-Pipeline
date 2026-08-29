"""User RBAC entity repository using Pure SQLAlchemy 2.0 ORM."""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import (
    EntityIdPrefix,
    UserRole,
    generate_entity_id,
)
from ..engine import get_db_session
from ..models import User


def create_user(
    email: str,
    full_name: str,
    role: str = UserRole.ADMIN.value,
    company_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> dict:
    """Creates a new user entity in the database with fail-fast uniqueness validation."""
    clean_email = email.strip().lower()
    clean_name = full_name.strip()
    clean_role = role.strip().upper() if role else UserRole.ADMIN.value
    uid = user_id or generate_entity_id(EntityIdPrefix.USER)
    now_str = datetime.now(timezone.utc).isoformat()

    try:
        with get_db_session() as session:
            stmt = select(User).filter_by(email=clean_email)
            existing = session.scalars(stmt).first()
            if existing:
                error_msg = f"User with email '{clean_email}' already exists."
                logger.error(error_msg)
                raise ValueError(error_msg)

            new_user = User(
                user_id=uid,
                company_id=company_id,
                email=clean_email,
                full_name=clean_name,
                role=clean_role,
                is_active=1,
                created_at=now_str
            )
            session.add(new_user)
            session.flush()
            logger.info(f"Created user '{clean_email}' with ID '{uid}' (Role: {clean_role}).")
            return new_user.to_dict()
    except Exception as e:
        logger.error(f"Failed to create user '{clean_email}': {e}")
        raise


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


def list_users(company_id: Optional[str] = None) -> list[dict]:
    """Lists users optionally filtered by company_id."""
    try:
        with get_db_session() as session:
            stmt = select(User)
            if company_id:
                stmt = stmt.filter_by(company_id=company_id)
            users = session.scalars(stmt).all()
            return [u.to_dict() for u in users]
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        return []
