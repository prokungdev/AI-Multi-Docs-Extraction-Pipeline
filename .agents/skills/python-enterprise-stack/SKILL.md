---
name: python-enterprise-stack
description: Enterprise Python 3.10+ development standards, Pure SQLAlchemy 2.0 ORM patterns, Dual Logging (Loguru + Database), Fail-Fast Pydantic v2 schemas, FastAPI Dependency Injection, and Async processing.
---

# Python Enterprise Stack & Architecture Standards

This skill documents the universal technology stack standards, design patterns, and architectural guidelines for Enterprise Python projects (Project-Agnostic).

---

## 1. Core Python Conventions & Code Hygiene

- **Python Version**: Python >= 3.10 (Optimized for Modern Python 3.10+ / 3.13+).
- **Type Annotations**: All functions must include complete Type Hints (`str`, `int`, `float`, `dict`, `list`, `Optional[T]`, `Generator[T, None, None]`).
- **Docstrings & Comments**: Must be written in **English only**. No local/regional non-ASCII characters in code comments, docstrings, or debug log statements.
- **Naming Conventions**:
  - `snake_case` for module names, function names, variable names, and database column names.
  - `PascalCase` for class names, Pydantic models, and SQLAlchemy ORM models.
  - `UPPER_SNAKE_CASE` for constants, threshold variables, and environment variable keys.
- **Centralized Constants Enforcement (Zero Magic Strings / Numbers)**:
  - Never scatter magic strings (status codes, domain identifiers, config paths) across codebase modules.
  - Centralize static constants in a dedicated `constants.py` module.
  - Use strongly-typed `Enum` classes for state machines and status transitions.
- **Strict Fail-Fast Configuration Principle**:
  - If a configuration parameter or threshold is defined in configuration files (e.g. `settings.json`, YAML), **do NOT provide silent fallback defaults in Python application logic**.
  - If a required configuration is missing or invalid, the system must fail immediately and loudly at boot time via Pydantic v2 schema validation (`model_validate()`).

---

## 2. Database Layer (Pure SQLAlchemy 2.0 ORM)

### Multi-Database URL Resolution Strategy
- **SQLite (Development/Testing)**: WAL mode, absolute path resolution relative to project root.
- **PostgreSQL / Cloud RDBMS (Production)**: Connection pooling via `create_engine(pool_size=..., max_overflow=..., pool_pre_ping=True)`.

### Pure SQLAlchemy 2.0 Model & Query Syntax
All database access must use modern, type-safe **Pure SQLAlchemy 2.0 Syntax** (`select()`, `insert()`, `update()`, `delete()`).

❌ **FORBIDDEN ANTI-PATTERNS (1.x Legacy & Raw SQL)**:
- `session.query(Model)` (Deprecated SQLAlchemy 1.x style)
- `cursor.execute("SELECT ...")` or `cursor.execute("INSERT ...")`
- `sqlite3.connect()` or ad-hoc raw SQL string concatenation

✅ **MANDATORY ENTERPRISE 2.0 ORM PATTERNS**:
```python
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import Session

# 1. Select Single Item
stmt = select(MasterRecord).filter_by(record_id=record_id)
record = session.scalars(stmt).first()

# 2. Select Multiple Items with Filtering and Sorting
stmt = (
    select(MasterRecord)
    .where(MasterRecord.status_code == RecordStatus.ACTIVE.value)
    .order_by(MasterRecord.created_at.desc())
)
records = session.scalars(stmt).all()

# 3. Aggregate Count
count_stmt = select(func.count()).select_from(MasterRecord).where(MasterRecord.is_active == 1)
total_count = session.scalar(count_stmt) or 0

# 4. Atomic Bulk Update
update_stmt = (
    update(MasterRecord)
    .where(MasterRecord.status_code == RecordStatus.PENDING.value)
    .values(status_code=RecordStatus.PROCESSED.value)
)
session.execute(update_stmt)

# 5. Bulk Delete
delete_stmt = delete(DetailItem).where(DetailItem.record_id == record_id)
session.execute(delete_stmt)
```

---

## 3. Session Lifecycle & FastAPI Dependency Injection

### Context Manager Pattern (For Pipeline / CLI Services)
```python
from contextlib import contextmanager
from typing import Generator
from sqlalchemy.orm import sessionmaker, Session

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager ensuring transactional commit, rollback on error, and cleanup."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

### FastAPI Dependency Injection Pattern (For REST API Layer)
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

def get_db_session_dep() -> Generator[Session, None, None]:
    """FastAPI Dependency for safe transactional session lifecycle."""
    with get_db_session() as session:
        yield session

@router.get("/items/{item_id}")
def get_item_endpoint(item_id: str, db: Session = Depends(get_db_session_dep)):
    stmt = select(ItemModel).filter_by(item_id=item_id)
    item = db.scalars(stmt).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item.to_dict()
```

---

## 4. Dual Logging Architecture (Loguru + Database Logs)

The system maintains a **Dual Logging System** to support both real-time developer debugging and persistent user auditability:

1. **Text Log File (`logs/app.log`)**:
   - Managed via `loguru`.
   - Rotates at 10 MB or daily, retained for 30 days.
   - Formatted with timestamps, log levels, module names, and function names.
2. **Database Application Logs**:
   - Stores user-facing activity logs, audit trails, and execution statuses.
   - Queryable via admin API endpoints for operational dashboards.
