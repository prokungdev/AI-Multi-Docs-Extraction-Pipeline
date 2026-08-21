---
name: python-enterprise-stack
description: Enterprise Python 3.10+ development standards, SQLAlchemy 2.0 ORM patterns, Dual Logging (Loguru + Database), Pydantic v2 schemas, Web UI integration, and Async processing.
---

# Python Enterprise Stack & Architecture Standards

This skill documents the mandatory technology stack standards, design patterns, and architectural guidelines for Enterprise Python projects.

---

## 1. Core Python Conventions & Code Hygiene

- **Python Version**: Python >= 3.10 (Optimized for Python 3.10+ / 3.13+).
- **Type Annotations**: All functions must include complete Type Hints (`str`, `int`, `float`, `dict`, `list`, `Optional[T]`).
- **Docstrings & Comments**: Must be written in **English only**. No local/regional non-ASCII characters in code comments, docstrings, or debug log statements.
- **Naming Conventions**:
  - `snake_case` for module names, function names, variable names, and database column names.
  - `PascalCase` for class names, Pydantic models, and SQLAlchemy ORM models.
  - `UPPER_SNAKE_CASE` for constants and environment variable keys.

---

## 2. Database Layer (SQLAlchemy 2.0 ORM)

### Multi-Database URL Resolution Strategy
- **SQLite (Development)**: `sqlite:///storage/app.db` (WAL mode, absolute path resolution relative to `PROJECT_ROOT`).
- **PostgreSQL / Cloud RDBMS (Production)**: Dynamically activated by setting `DB_URL_OVERRIDE` or `DATABASE_URL` in `.env` (e.g. `postgresql://user:pass@localhost:5432/appdb`).

### ORM Model Definition Pattern
All database tables must inherit from `sqlalchemy.orm.declarative_base()`:

```python
from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class MasterRecord(Base):
    """Master record header model."""
    __tablename__ = "master_records"

    record_id = Column(String(100), primary_key=True)
    title = Column(String(200), nullable=False)
    status_code = Column(String(50), nullable=False)
    subtotal = Column(Float, default=0.0, server_default="0.0")
    net_amount = Column(Float, default=0.0, server_default="0.0")

    items = relationship("DetailItem", back_populates="master", cascade="all, delete-orphan")
```

### Session Lifecycle & Context Management
Always use a `get_db_session()` context manager for transaction safety, automatic commit, rollback on error, and proper session closure:

```python
from core.db.connection import get_db_session

def fetch_active_record(record_id: str) -> dict | None:
    """Fetch record details using SQLAlchemy session."""
    with get_db_session() as session:
        record = session.query(MasterRecord).filter(MasterRecord.record_id == record_id).first()
        if record:
            return {"record_id": record.record_id, "title": record.title}
    return None
```

---

## 3. Dual Logging Architecture (Loguru + Database Logs)

The system maintains a **Dual Logging System** to support both real-time developer debugging and persistent user auditability:

1. **Text Log File (`logs/app.log`)**:
   - Managed via `loguru`.
   - Rotates at 10 MB or daily, retained for 30 days.
   - Formatted with timestamps, log levels, module names, and function names.
2. **Database Application Logs (`logs/logs.db`)**:
   - Structured table `application_logs` storing `log_id`, `level`, `message`, `module`, `function`, and `created_at`.
   - Queryable via Web UI / Monitoring dashboard for admin monitoring and audit reports.

---

## 4. Data Validation (Pydantic v2)

- All external API inputs, configuration files, and extracted payload dictionaries must be validated against a Pydantic `BaseModel`.
- Data field validations and field sanitization must run before saving to the database.

---

## 5. Web UI & Document Processing

- **Web Framework**: State management, decoupled DB calls via database abstraction modules.
- **File Hashing**: Use SHA-256 binary hash (`calculate_file_hash`) for duplicate content detection before processing.

---

## 6. Code Review Checklist Integration

When performing code reviews using `code-reviewer`, ensure:
1. Database calls use `get_db_session()` or `SQLAlchemy ORM` instead of raw un-parameterized SQL strings.
2. Docstrings and comments are in English.
3. Errors are logged via `loguru.logger` and stored in persistent application logs.
4. File paths resolve dynamically using `Path` or `PROJECT_ROOT`.
