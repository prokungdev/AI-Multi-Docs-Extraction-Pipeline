---
name: python-enterprise-stack
description: Enterprise Python 3.10+ development standards, SQLAlchemy 2.0 ORM patterns, Dual Logging (Loguru + SQLite DB), Pydantic v2 schemas, Streamlit Web UI, and PyMuPDF document processing.
---

# Python Enterprise Stack & Architecture Standards

This skill documents the mandatory technology stack standards, design patterns, and architectural guidelines for the **AI Multi-Docs Extraction Pipeline** project.

---

## 1. Core Python Conventions & Code Hygiene

- **Python Version**: Python >= 3.10 (Tested & optimized for Python 3.13+).
- **Type Annotations**: All functions must include complete Type Hints (`str`, `int`, `float`, `dict`, `list`, `Optional[T]`).
- **Docstrings & Comments**: Must be written in **English only**. No Thai characters in code comments, docstrings, or debug log statements.
- **Naming Conventions**:
  - `snake_case` for module names, function names, variable names, and database column names.
  - `PascalCase` for class names, Pydantic models, and SQLAlchemy ORM models.
  - `UPPER_SNAKE_CASE` for constants and environment variable keys.

---

## 2. Database Layer (SQLAlchemy 2.0 ORM)

### Multi-Database URL Resolution Strategy
- **SQLite (Development)**: `sqlite:///pipeline_storage/pipeline.db` (Wal mode, absolute path resolution relative to `PROJECT_ROOT`).
- **PostgreSQL (Production)**: Dynamically activated by setting `DB_URL_OVERRIDE` or `DATABASE_URL` in `.env` (e.g. `postgresql://user:pass@localhost:5432/pipelinedb`).

### ORM Model Definition Pattern
All database tables must inherit from `sqlalchemy.orm.declarative_base()`:

```python
from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class ExpenseReceipt(Base):
    """Expense receipt header model."""
    __tablename__ = "expense_receipt"

    receipt_id = Column(String(100), primary_key=True)
    document_id = Column(String(100), ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False)
    merchant_name = Column(String(200), nullable=True)
    subtotal = Column(Float, default=0.0, server_default="0.0")
    vat_amount = Column(Float, default=0.0, server_default="0.0")
    net_amount = Column(Float, default=0.0, server_default="0.0")

    items = relationship("ExpenseReceiptItem", back_populates="receipt", cascade="all, delete-orphan")
```

### Session Lifecycle & Context Management
Always use the `get_db_session()` context manager for transaction safety, automatic commit, rollback on error, and proper session closure:

```python
from src.core.db.connection import get_db_session

def fetch_active_merchant(merchant_id: str) -> dict | None:
    """Fetch merchant details using SQLAlchemy session."""
    with get_db_session() as session:
        merchant = session.query(MerchantMaster).filter(MerchantMaster.merchant_id == merchant_id).first()
        if merchant:
            return {"merchant_id": merchant.merchant_id, "name": merchant.merchant_name}
    return None
```

---

## 3. Dual Logging Architecture (Loguru + SQLite DB)

The system maintains a **Dual Logging System** to support both real-time developer debugging and persistent user auditability:

1. **Text Log File (`logs/app.log`)**:
   - Managed via `loguru`.
   - Rotates at 10 MB or daily, retained for 30 days.
   - Formatted with timestamps, log levels, module names, and function names.
2. **SQLite Database Logs (`logs/logs.db`)**:
   - Structured table `application_logs` storing `log_id`, `level`, `message`, `module`, `function`, and `created_at`.
   - Queryable via Streamlit Web UI for admin monitoring and audit reports.

---

## 4. Data Validation (Pydantic v2)

- All JSON data extracted by AI models (Gemini Flash/Pro) must be validated against a Pydantic `BaseModel`.
- Financial field validations (Subtotal + VAT = Net Amount) must run before saving to the database.

---

## 5. Web UI (Streamlit) & Document Processing

- **Streamlit**: State management (`st.session_state`), decoupled DB calls via `src/core/db/` modules.
- **PyMuPDF (`fitz`)**: Render PDF pages to high-resolution JPG images (150 DPI).
- **File Hashing**: Use SHA-256 binary hash (`calculate_file_hash`) for duplicate document detection before processing.

---

## 6. Code Review Checklist Integration

When performing code reviews using `code-reviewer`, ensure:
1. Database calls use `get_db_session()` or `SQLAlchemy ORM` instead of raw un-parameterized SQL strings.
2. Docstrings and comments are in English.
3. Errors are logged via `loguru.logger` and stored in `logs/logs.db`.
4. File paths resolve dynamically using `Path` or `PROJECT_ROOT`.
