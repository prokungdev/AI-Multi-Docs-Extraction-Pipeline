---
name: database-architect
description: >-
  Enterprise relational database architecture standards, Pure SQLAlchemy 2.0 ORM patterns,
  standardized table and column naming conventions, migrations, indexing, and cascade relationships.
---

# 🏛️ Database Architect Skill

This skill defines universal enterprise database design standards, table/column naming conventions, Pure SQLAlchemy 2.0 ORM patterns, and testing resource lifecycle management.

---

## 📐 1. Table & Column Naming Conventions

All relational database models and schema definitions MUST strictly follow these enterprise naming rules:

### 1.1 Table Names
- **Plural & `snake_case`**: Always use plural English nouns in `snake_case` (e.g., `merchants`, `documents`, `orders`, `order_items`).
- **NO Cryptic Abbreviations**: Never use legacy abbreviations (e.g., do NOT use `_d` for detail tables; use `_items` or `_details` instead).
- **NO Singular + Suffix Mixes**: Do NOT use `merchant_master`; use `merchants` (or `merchant_masters` consistently).

### 1.2 Column Names
- **Primary Keys**: Always format as **`{singular_table}_id`** (e.g., `user_id`, `document_id`, `order_id`, `item_id`, `page_id`, `log_id`).
- **Foreign Keys**: Always match the primary key name of the referenced table (e.g., `batch_id`, `document_id`, `order_id`, `user_id`).
- **Status Columns**: Standardize on **`status_code`** across all entities (e.g., `documents.status_code`, `users.status_code`, `api_call_logs.status_code`).
- **Timestamp Columns**: Standardize on **`created_at`** and **`updated_at`** (UTC ISO format string or DateTime). Never use unstructured `timestamp` or `time`.
- **Boolean Flags**: Must start with **`is_`** prefix (e.g., `is_active`, `is_locked`, `is_manually_edited`, `is_auto_approved`, `is_verified`).
- **Financial & Quantity Fields**: Use explicit full words (e.g., `quantity`, `unit_price`, `subtotal`, `discount_amount`, `vat_amount`, `net_amount`).

---

## 💾 2. Pure SQLAlchemy 2.0 ORM Policy

1. **Context Manager Access**:
   All database operations MUST execute inside a session context:
   ```python
   from sqlalchemy import select
   from my_app.core.db import get_db_session, MasterEntity

   with get_db_session() as session:
       stmt = select(MasterEntity).filter_by(entity_code=entity_code)
       entity = session.scalars(stmt).first()
   ```
2. **Forbidden Anti-Patterns**:
   - ❌ `session.query(Model)` (Deprecated SQLAlchemy 1.x style)
   - ❌ `cursor.execute("SELECT ...")` in business logic
   - ❌ `sqlite3.connect(...)` in business logic
   - ❌ Raw string formatting in SQL queries (SQL Injection risk)
3. **Serialization Standard**:
   - All entity models should provide a `.to_dict()` helper or Pydantic `from_attributes = True` for clean decoupled serialization.

---

## 🔗 3. Relationships, Foreign Keys & Cascades

1. **Explicit Cascade Rules**:
   Child tables (items, sub-records) must specify explicit cascade behavior:
   ```python
   # On parent model:
   items = relationship("DetailItem", back_populates="header", cascade="all, delete-orphan")
   
   # On child model:
   header_id = Column(String(100), ForeignKey("headers.header_id", ondelete="CASCADE"), nullable=False)
   ```
2. **Indexing Strategy**:
   - Add explicit indexes (`Index("idx_...", ...)`) on all query-filter and search columns (`status_code`, `created_at`, foreign keys, search keys).

---

## 🔄 4. Schema Evolution & Safe Migrations

1. **Declarative Creation**: `Base.metadata.create_all(engine)` is the foundation for creating all tables.
2. **Lightweight Safe Migrations**: When adding new columns, inspect existing tables and execute `ALTER TABLE ... ADD COLUMN` safely without dropping tables or losing data.

---

## 🛡️ 5. Windows OS Resource Cleanup in Unit Tests

When running automated test suites on Windows operating systems, SQLite file locks can prevent temporary test databases from being deleted in `tearDownClass`.

**Mandatory Test Fixture Teardown Pattern:**
```python
import os
import gc
import unittest
from my_app.core.db import get_engine

class BaseDatabaseTestCase(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        # 1. Dispose engine connections and connection pool
        get_engine().dispose()
        
        # 2. Force garbage collection to release any remaining connection handles
        gc.collect()
        
        # 3. Safely remove test database file without PermissionError
        if hasattr(cls, "test_db_path") and os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass
```

---

## 🗑️ 6. Dormant / Dead Table Pruning & Anti-Patterns

1. **Prune Superseded Tables**:
   - When an application architecture evolves such that specific database tables are superseded by configuration schemas, environment variables, or centralized metadata gateways, the obsolete entity models and tables MUST be cleanly pruned.
   - Do NOT retain dormant models or uncalled database structures that are disconnected from active business workflows.
2. **Clean Query Helpers & Module Exports**:
   - When dropping or retiring an entity model, all associated query helper functions, CRUD operations, and module exports in package `__init__.py` MUST be purged to eliminate dead code and invalid import risks.

---

## 🔄 7. Seed Data Synchronization & Code Constants Alignment

1. **Strict Reference Table Parity**:
   - Master reference tables seeded at system initialization (such as status codes, state machines, category lookups) MUST strictly mirror the application's centralized constants or strongly-typed Enums.
   - **Zero State Drift Policy**: Every valid state or status code defined in business constants MUST exist in the corresponding database reference seed data.
2. **Automated Column Migration for Schema Evolution**:
   - When columns are renamed during model refactoring, the schema initialization routine MUST provide safe, automated schema migrations (e.g., `ALTER TABLE ... RENAME COLUMN`) to preserve existing database integrity and prevent runtime query errors.

---

## 🗄️ 8. Dual-Database Isolation: Operational vs Diagnostic Data

1. **Storage Segregation**:
   - High-throughput diagnostic logs (e.g., application event logs, system traces) MUST be isolated into a dedicated logging database file or storage cluster separate from the primary operational database (e.g. primary relational cluster / file).
   - Prevents log volume surges from locking transactional business tables or bloating operational databases.
2. **Distinct Declarative Metadata Bases**:
   - Use distinct SQLAlchemy declarative metadata bases (e.g., `Base` for business domain entities, `LogBase` for logging and diagnostic entities) with isolated database engines and session factories.
3. **Drop & Recreate Lifecycle Policy**:
   - Schema initialization routines SHOULD provide a controlled `drop_and_recreate: bool = False` flag to allow developers and automated test harnesses to cleanly purge and re-bootstrap fresh operational tables on demand.
