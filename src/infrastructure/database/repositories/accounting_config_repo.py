"""Accounting & Destination Target System Configuration Repository.

Provides Pure SQLAlchemy 2.0 ORM operations for:
- ExpenseAccountMapping lookup and management
- ExpenseType master lookup
- TargetSystem and IntegrationMethod registries
"""

from typing import Optional, List, Dict, Any
from sqlalchemy import select, and_

from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import (
    EntityIdPrefix,
    SystemUserId,
    generate_entity_id,
)
from ..engine import get_db_session
from ..models import (
    ExpenseAccountMapping,
    ExpenseType,
    TargetSystem,
    IntegrationMethod,
)


def get_expense_account_mapping(
    company_id: str,
    target_system_id: str,
    expense_type_name: str,
) -> Optional[Dict[str, Any]]:
    """Retrieves GL account mapping for a specific company, target ERP system, and expense type."""
    if not company_id or not target_system_id or not expense_type_name:
        return None

    with get_db_session() as session:
        stmt = select(ExpenseAccountMapping).where(
            and_(
                ExpenseAccountMapping.company_id == company_id,
                ExpenseAccountMapping.target_system_id == target_system_id,
                ExpenseAccountMapping.expense_type_name == expense_type_name.strip(),
            )
        )
        mapping = session.scalars(stmt).first()
        return mapping.to_dict() if mapping else None


def list_expense_account_mappings(
    company_id: str,
    target_system_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lists all GL account mappings for a company, optionally filtered by target system."""
    if not company_id:
        return []

    with get_db_session() as session:
        stmt = select(ExpenseAccountMapping).where(ExpenseAccountMapping.company_id == company_id)
        if target_system_id:
            stmt = stmt.where(ExpenseAccountMapping.target_system_id == target_system_id)
        mappings = session.scalars(stmt.order_by(ExpenseAccountMapping.expense_type_name.asc())).all()
        return [m.to_dict() for m in mappings]


def upsert_expense_account_mapping(
    company_id: str,
    target_system_id: str,
    expense_type_name: str,
    account_code: str,
    account_name: Optional[str] = None,
    department_code: str = "",
) -> Dict[str, Any]:
    """Creates or updates a GL account mapping for a company and target system."""
    if not company_id or not target_system_id or not expense_type_name or not account_code:
        raise ValueError("company_id, target_system_id, expense_type_name, and account_code are required.")

    with get_db_session() as session:
        stmt = select(ExpenseAccountMapping).where(
            and_(
                ExpenseAccountMapping.company_id == company_id,
                ExpenseAccountMapping.target_system_id == target_system_id,
                ExpenseAccountMapping.expense_type_name == expense_type_name.strip(),
            )
        )
        mapping = session.scalars(stmt).first()
        if mapping:
            mapping.account_code = account_code.strip()
            if account_name is not None:
                mapping.account_name = account_name.strip()
            mapping.department_code = department_code.strip() if department_code else ""
            logger.info(f"Updated expense account mapping: {expense_type_name} -> {account_code}")
        else:
            mapping = ExpenseAccountMapping(
                mapping_id=generate_entity_id(EntityIdPrefix.EXPENSE_ACCOUNT_MAPPING),
                company_id=company_id,
                target_system_id=target_system_id,
                expense_type_name=expense_type_name.strip(),
                account_code=account_code.strip(),
                account_name=account_name.strip() if account_name else None,
                department_code=department_code.strip() if department_code else "",
                created_by=SystemUserId.SYSTEM_ADMIN,
            )
            session.add(mapping)
            logger.info(f"Created expense account mapping: {expense_type_name} -> {account_code}")
        session.flush()
        return mapping.to_dict()


def get_expense_type(expense_type_name: str) -> Optional[Dict[str, Any]]:
    """Retrieves an expense type master record by name."""
    if not expense_type_name:
        return None

    with get_db_session() as session:
        stmt = select(ExpenseType).where(ExpenseType.expense_type_name == expense_type_name.strip())
        exp_type = session.scalars(stmt).first()
        return exp_type.to_dict() if exp_type else None


def list_expense_types() -> List[Dict[str, Any]]:
    """Lists all active expense types."""
    with get_db_session() as session:
        stmt = select(ExpenseType).where(ExpenseType.is_active == 1).order_by(ExpenseType.expense_type_name.asc())
        types = session.scalars(stmt).all()
        return [t.to_dict() for t in types]


def get_target_system(system_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a target system record by system_id."""
    if not system_id:
        return None

    with get_db_session() as session:
        stmt = select(TargetSystem).where(TargetSystem.system_id == system_id.strip())
        system = session.scalars(stmt).first()
        return system.to_dict() if system else None


def list_target_systems() -> List[Dict[str, Any]]:
    """Lists all active target systems."""
    with get_db_session() as session:
        stmt = select(TargetSystem).where(TargetSystem.is_active == 1).order_by(TargetSystem.system_id.asc())
        systems = session.scalars(stmt).all()
        return [s.to_dict() for s in systems]
