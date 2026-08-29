# Project Architecture & Quick Map

## 1. Canonical Domain-Driven Design (DDD) Structure
- `src/domain/`: Pure business rules & in-memory domain services (Zero DB / I/O)
  - `policies/`: Business rule specifications & validation engine
    - `financial_rules.py`: Math balance, VAT 7%, WHT, and Confidence scoring (`ValidationStrategyEngine`)
  - `services/`: Pure string & mapping algorithms
    - `text_normalizer.py`: Short name sanitization & Thai Buddhist Era (พ.ศ.) date parser
    - `template_evaluator.py`: JSON template record transformer (`get_nested_value`, `transform_data`)
  - `entities/`: Domain entities & aggregates
- `src/application/`: Use cases & pipeline orchestration
  - `pipeline/`: Stages 0 to 4 (`stage_0_init`, `stage_1_ingestion`, `stage_2_extraction`, `stage_3_transformation`, `stage_4_validation`)
  - `usecases/`: 100% Symmetrical Stage Use Cases:
    - `initializer.py`: Stage 0 system & storage bootstrap
    - `classifier.py`: Stage 1 zero-cost prefix & multi-tenant routing
    - `extractor.py`: Stage 2 multimodal AI prompting & token math
    - `transformer.py`: Stage 3 relational database conversion
    - `validator.py`: Stage 4 multi-rule validation, confidence scoring & archiving
  - `exporters/`: Output Strategy Adapters & Dynamic Registry:
    - `base.py`: Base Strategy Interface (`BaseOutputExporter`)
    - `express_adapter.py`: Express CP874 PV with voucher running numbers
    - `json_adapter.py`: Google Sheet & Line Items summary
    - `registry.py`: Dynamic Exporter Registry (`list_exporters`, `get_exporter`)
  - `dtos/`: Pydantic V2 schemas (`settings_dto.py`, `document_dto.py`)
- `src/infrastructure/`: Technical adapters & external persistence (Organized in 3 Enterprise Pillars)
  - `database/`: 🗄️ **เสาหลักที่ 1: Database & Data Access**
    - `engine.py`: Engine, Session Pool, Dispose, Connection lifecycle
    - `models.py`: Pure SQLAlchemy 2.0 ORM Entities (`Company`, `User`, `DocumentControl`, `Batch`, `BatchPage`, `Merchant`, `ExpenseReceipt`, etc.)
    - `schema.py`: DDL Initializer & DB Reset
    - `seeder.py`: Initial Master Data Seeders (Default Tenant, Statuses, Default Users)
    - `repositories/`: Single-responsibility Repository layer
      - `batch_repo.py`: Ingestion Batches & Chunk Pages
      - `document_repo.py`: DocumentControl Supertype & 15-min Leases
      - `receipt_repo.py`: ExpenseReceipt Subtype & Relational Items
      - `merchant_repo.py`: Merchant Gatekeeper & Matching
      - `company_repo.py`: Tenant Company Master CRUD
      - `user_repo.py`: RBAC User Management
  - `external/`: 🔌 **เสาหลักที่ 2: External Adapters & Third-party Services**
    - `ai/`: Gemini LLM Client & Token Cost Math (`ai_service.py`, `cost_estimator.py`)
    - `pdf/`: PyMuPDF Splitting, Image Resizing (`pdf_service.py`, `image_service.py`)
    - `storage/`: Local/S3 Disk Storage Driver (`base.py`, `local_adapter.py`, `storage_manager.py`)
  - `core/`: ⚙️ **เสาหลักที่ 3: Cross-Cutting Core Utilities**
    - `constants.py`: Enums, Defaults, Status Codes
    - `logger.py`: Universal Logging Gateway
    - `config.py`: Pure Settings Loader (Zero DB dependency)
    - `lock.py`: Pipeline Process File Lock
    - `telemetry.py`: API Call Telemetry & Audit Logs
    - `healthcheck.py`: System Readiness & Database Diagnostic Probes
    - `utils.py`: Chunking & Short Name Utilities
- `apps/`: Presentation & delivery mechanisms
  - `api/`: FastAPI REST endpoints & dependency injection
  - `streamlit/`: Streamlit web UI dashboard
- `configs/`: `settings.json` (Validated by `SystemSettingsModel`) & `doc_types/`
- `storage/`: `database/` (`pipeline.db`) & `companies/` (Tenant data folders)

## 2. Pipeline Workflow (Per-Batch Concurrency Isolation)
1. **Stage 0 (`init_system`)**: Validates config & initializes DB/storage.
2. **Stage 1 (`split_and_match`)**: Splits PDF to JPGs, computes SHA-256, matches merchant rules, outputs `batch_id`.
3. **Stage 2 (`extract_documents(batch_id)`)**: Multimodal AI extraction + token cost calculation for target batch.
4. **Stage 3 (`transform_to_db(batch_id)`)**: Inserts normalized records into SQLite via SQLAlchemy 2.0 for target batch.
5. **Stage 4 (`validate_documents(batch_id)`)**: Verifies financial math balance & confidence scores for target batch.
6. **Exporters (`run_export_outputs`)**: Generates CSV, JSON, and CP874 Express PV files.

## 3. Database & Persistence Layer (Multi-Database Support)
- **Engines**: SQLite (Default / Dev / Edge) ⇄ PostgreSQL / MySQL (Production / Cloud)
- **Auto Schema Init**: `initialize_db_schema()` via Pure SQLAlchemy 2.0 `Base.metadata.create_all()`
- **Lifecycle & Concurrency Architecture**:
  - **Lifecycle Finalization (`is_closed`)**: Atomic guard (`is_closed == 0`) seals approved/rejected documents against post-approval modifications.
  - **Airline Ticket Hold Concurrency (`is_locked`, `locked_by`, `locked_at`)**: 15-minute exclusive editing lease with heartbeat renewal and automatic expiration/release to prevent stale locks.
  - **Smart Chunk Checkpointing (`batch_pages.chunk_index`)**: Multi-page PDF extraction tracks chunk-level progress (`PENDING` ➔ `EXTRACTED` / `FAILED`), caching completed chunks and allowing instant resuming for failed segments.

## 4. Test Suite (Targeted Testing Protocol & Two-Tier Test Harness)
- **Two-Tier Test Isolation Guard**:
  - **Tier 1 (Root Guard `tests/conftest.py`)**: Session-level isolation redirecting all DB operations to temporary SQLite database, setting `TEST_ENVIRONMENT="1"` and `APP_ENV="testing"` to bypass disk logging DB sink.
  - **Tier 2 (Integration Guard `tests/integration/conftest.py`)**: Package-level fixture initializing schema (`initialize_db_schema()`) and seeding master data (`seed_initial_data()`) exclusively for integration tests.
- **Environment-Aware Logging Gateway**: Bypass DB sink during testing to eliminate SQLite lock contention and maximize execution speed.
- **Targeted Test Commands**:
  - Run all tests: `pytest tests/ -v` (114 unit & integration tests, 100% Passed)
  - Run unit tests (offline & pure logic): `pytest tests/unit -v`
  - Run integration tests (DB & pipeline): `pytest tests/integration -v`
