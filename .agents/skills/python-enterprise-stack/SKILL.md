---
name: python-enterprise-stack
description: Enterprise Python 3.10+ development standards, Pure SQLAlchemy 2.0 ORM patterns, Universal Dual Logging Gateway (Diagnostic + Database Audit Wrapper), Fail-Fast Pydantic v2 schemas, FastAPI Dependency Injection, and Async processing.
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
- **Strict Fail-Fast Configuration & Secret Principle**:
  - Never guess or provide silent fallback defaults for missing secrets, credentials, environment variables, or database paths (e.g. `.get("api_key_env", "DEFAULT_KEY")` or `return {}` on file load failure).
  - If a required configuration is missing or invalid, the system must fail immediately and loudly at boot time via Pydantic v2 schema validation (`model_validate()`) or explicit descriptive Exceptions (`ValueError`, `FileNotFoundError`, `KeyError`).
  - Safe defaults are permitted ONLY for data normalization (e.g. `0.0` for optional numerical fields) or documented performance tuning constants.
- **Single Canonical API & Zero Redundant Aliases Policy**:
  - Never retain module-level function aliases, wrapper functions, or class/property aliases solely for internal backward compatibility (e.g. `legacy_func = new_func`, `def old_func(): return new_func()`).
  - Eliminate vocabulary drift across codebase layers: enforce a single, canonical naming convention across all modules, schemas, database models, and API endpoints.
  - Consumers must import and invoke canonical functions directly without intermediate legacy translation layers.
- **High-Signal Commenting & Docstring Hygiene**:
  - **Explain WHY, not WHAT**: Code and type hints explain what and how; comments exist strictly to explain why (rationale, business rules, edge cases, workarounds, or mathematical formulas).
  - **Zero Noise & Obvious Boilerplate**: Never restate what the code clearly does (e.g. avoid comments like `# load json`, `# check if file exists`, or repetitive `Fail-Fast: Raises ...` above standard guard clauses).
  - **Concise Single-Line Docstrings**: Use crisp, single-line docstrings for self-evident helper and utility functions. Multi-line docstrings are reserved for complex public interfaces with non-obvious side effects or complex parameter schemas.
  - **No Step Spamming on Simple Logic**: Avoid numbering trivial 1-line operations (`# 1. do A`, `# 2. do B`) inside short functions.

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

## 4. Dual Logging Architecture & Logging Gateway Pattern

The system enforces an enterprise **Dual Logging Architecture** with a decoupled **Logging Gateway (Adapter Pattern)** to eliminate vendor lock-in and support both real-time diagnostics and persistent auditability:

### 1. Decoupled Logging Gateway (Wrapper Pattern)
- **Centralized Entry Point**: All application and business modules must import and use the project's internal **Logger Gateway / Wrapper** rather than importing third-party logging libraries directly.
- **Uniform Interface**: Exposes standardized logging methods (`debug()`, `info()`, `warning()`, `error()`, `exception()`, `bind()`).
- **Backend Swappability**: Changing the underlying logging engine (console, rotating file, remote collector) is isolated strictly within the logger gateway module without touching any business code.

### 2. Dual Sink Strategy
- **Diagnostic Text Logs**:
  - Console and rotating file sinks for real-time developer debugging.
  - Automatically captures timestamps, log levels, module names, and function context.
- **Audit & Database Telemetry Logs**:
  - Persistent database tables for user-facing activity logs, API execution metrics, token cost telemetry, and audit trails.
  - Queryable via administration APIs and operational monitoring dashboards.

### 3. Structured Audit Logging (DTO Pattern)
- Database and telemetry logging must pass strongly-typed **Data Transfer Objects (DTO) / Schemas** rather than loose multi-argument parameters, ensuring type safety, validation, and schema evolution.

### 4. Diagnostic vs Operational Log Storage Segregation
- High-volume diagnostic log streams captured by database sinks MUST be routed to a dedicated logging database or storage cluster (via isolated session managers) rather than the primary operational database, preventing lock contention and uncontrolled business database growth.

---

## 5. Third-Party Processing Engine Adapters & Service Wrappers

To avoid vendor lock-in, resource leaks, and tight coupling across business logic:

### 1. Mandatory Service Wrapper for Multi-File Dependencies
- Any third-party processing engine that is used across multiple modules (e.g. PDF processing, image transformation, optical text extraction, external API clients) **MUST be encapsulated behind an internal Service Wrapper / Adapter Layer** (e.g. `PDFService`, `ImageService`, `AIService`).
- Business logic modules must never import or invoke complex third-party C-bindings or libraries directly.

### 2. Lifecycle & Safe Resource Management
- Service wrappers must manage underlying file descriptors, memory buffers, and C-extension handles safely via **Context Managers** (`__enter__` / `__exit__`), guaranteeing immediate cleanup and preventing OS file locks (especially on Windows).

---

## 6. Namespaced Constants Classes & Cascading Parameter Resolvers

To maintain clean architecture, avoid floating global variables, and eliminate copy-pasted parameter fallback logic:

### 1. Namespaced Constants Classes
- **Class-Grouped Constants**: Group related static constants into dedicated, typed namespace classes rather than leaving loose, scattered uppercase variables:
  - System and filesystem path container classes (e.g. `DefaultPath` / `SystemPaths`).
  - Entity identifiers and fallback labels container classes (e.g. `DefaultIdentifier` / `SystemIdentifiers`).
  - Application metadata container classes (e.g. `AppMetadata`).
  - State machine lifecycle actions and entity status codes (`Enum` or namespace classes).

### 2. Zero Static Aliases Policy (Anti-Pattern Prevention)
- **Eliminate Dual Import Ambiguity**: Once enterprise namespaced classes are established, do NOT maintain lingering flat module-level static aliases (e.g., `DEFAULT_PATH = DefaultPath.PATH`).
- **Direct Namespace Consumption**: All consumer modules, services, and test suites MUST import and access constants directly via their namespaced classes (e.g. `DefaultPath.SETTINGS`), preventing split terminology and obsolete legacy bridges.

### 3. Cascading Parameter Resolvers (DRY Principle)
- When multiple pipeline stages or services resolve cascading defaults (e.g. resolving target tenant ID, entity scope, or processing domain), **MUST create centralized resolver functions** rather than repeating ternary fallback expressions across multiple caller files.

### 4. Prefixed Entity Identifier Standard (Stripe-Style / TypeID Pattern)
- **Standard Format**: Primary keys and external entity identifiers MUST follow the standardized prefixed pattern: `<entity_prefix>_<entropy_hex>` (e.g. `12` to `16` hexadecimal characters generated from UUID4, such as `doc_c4e5a5799901`, `comp_b8f2a1d933e4`).
- **Centralized Entity Prefixes**: Define all entity prefixes in a dedicated constants namespace class (e.g., `EntityIdPrefix`).
- **Unified Generator Utility**: Centralize ID creation via a standard helper (e.g. `generate_entity_id(prefix, hex_length=12)`) instead of ad-hoc string concatenations scattered across modules.
- **Benefits**: Guarantees high observability in logs, visual type-safety preventing cross-entity ID bugs in REST APIs, compact index storage, and zero cross-machine collision probability.

---

## 7. Dynamic Schema & Dead Model Elimination

- **Dynamic Payload vs Static Pydantic Models**: When an enterprise system adopts dynamic JSON Schemas or runtime schema-driven extraction, eliminate dead/unused static payload Pydantic models from domain model modules to prevent dead code accumulation and schema divergence.
- **Legacy Fallback Directory Purge**: When directory layouts or naming standards are migrated, purge old fallback lookups to deleted/deprecated directory layouts (`if not os.path.exists("new_dir"): return "old_dir"`) to establish a single, unambiguous Source of Truth.

---

## 8. Dynamic Configuration Verification & Boot-Time Probing

To ensure rock-solid production readiness and fail-fast guarantees:

### 1. Cross-Field Hierarchy & Semantic Parity
- Use schema-level model validators (e.g. `@model_validator(mode="after")`) to verify relational constraints across distinct configuration blocks:
  - **Threshold Hierarchies**: Ensure ordered thresholds (e.g., `low <= review <= high`) are logically consistent.
  - **Dependent Block Parity**: Ensure that active entity or model names selected in provider configurations exist in associated rate cards or pricing tables.

### 2. Dynamic Environment & Driver Resolution
- Application initialization must dynamically resolve environment variable keys from schema definitions (e.g., driver-specific URL keys or provider-specific credential keys) rather than hardcoding static environment variable names in boot scripts.

### 3. Storage & Resource Write-Permission Probing
- Boot-time health checks and initialization routines MUST execute non-destructive write/remove probes (e.g., creating and cleaning a `.probe.tmp` file) on configured storage roots and log directories to catch permission errors before user workloads arrive.

### 4. Bidirectional Asset & Schema Sync
- Verify that active features, templates, or domain types declared in configuration files have corresponding physical asset directories and schema definitions on disk, while flagging orphaned assets.

---

## 9. Modular Sub-Package Layering & Clean Core Architecture

To avoid monolithic or flat core folders (where infrastructure, external services, data models, and business logic intermingle), enterprise Python codebases must organize the core engine into distinct, single-responsibility sub-packages:

### 1. Standard Sub-Package Taxonomy
- **`common/` (or `infra/`)**: Cross-cutting foundation independent of business domain:
  - Centralized constants & state enums (`constants.py`)
  - Universal dual logging gateway (`logger.py`)
  - Configuration loaders (`config_loader.py`)
  - Shared utility functions & hashers (`utils.py`)
  - Health checks & system probes (`healthcheck.py`)
- **`services/`**: External adapters, SDK integrations, and domain engine services:
  - Third-party API / LLM clients (e.g. `ai_service.py`)
  - Document rendering & file conversion services (e.g. `pdf_service.py`, `pdf_splitter.py`)
  - Cost, token, or metering engines (`cost_estimator.py`)
  - Multi-tenant directory & path managers (`storage_manager.py`)
- **`processors/`**: Business logic, rule engines, and data pipeline components:
  - Workspace / tenant bootstrappers (`initializer.py`)
  - Document / message classifiers (`classifier.py`)
  - Structured extraction engines (`extractor.py`)
  - Normalization & payload enrichment (`transformer.py`)
  - Post-processing, tax calculation, and data balancing (`post_processor.py`)
- **`schemas/`**: Pydantic v2 Data Transfer Objects (DTOs), API contracts, and validation models:
  - System configuration models (`settings_schema.py`)
  - Transactional payload models & DTOs (`document_schemas.py`)
- **`db/`**: Pure SQLAlchemy 2.0 ORM layer:
  - Database connection & session dependencies (`connection.py`)
  - Database schema definitions & tables (`schema.py`)
  - Pure SQLAlchemy 2.0 Entities (`models.py`)
  - Repository & master data access functions (`masters.py`, `documents.py`, `logs.py`)

### 2. Unambiguous Model Separation Rule
- **Never create ambiguous `models.py` at the package root**: Avoid mixing Pydantic schemas and database entities in the same file or package level.
- **Strict Separation**:
  - **SQLAlchemy ORM Entities** reside exclusively in `db/models.py`.
  - **Pydantic Validation Models & DTOs** reside exclusively in `schemas/`.

### 3. Facade Pattern for Public API Export
- The top-level package `__init__.py` acts as an enterprise **Facade Interface**, re-exporting canonical classes and functions from sub-packages.
- This guarantees a clean, stable public API surface while allowing sub-packages to evolve internally without breaking external consumers.

