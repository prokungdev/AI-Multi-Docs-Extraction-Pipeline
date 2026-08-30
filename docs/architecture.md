# Project Architecture & Quick Map

## 1. Canonical Domain-Driven Design (DDD) Structure
- `src/domain/`: Pure business rules & in-memory domain services (Zero DB / I/O)
  - `doc_types/`: 📑 **Domain Document Types Strategy & Registry**
    - `base.py`: Abstract Base Class (`BaseDocType`)
    - `registry.py`: Centralized Registry (`DocTypeRegistry`, `get_doc_type`, `list_doc_types`, `get_active_doc_types`)
    - `expense_receipt.py`: `ExpenseReceiptDocType` (`DocTypeId.EXPENSE_RECEIPT`)
    - `tax_invoice.py`: `TaxInvoiceDocType` (`DocTypeId.TAX_INVOICE`)
    - `withholding_tax.py`: `WithholdingTaxDocType` (`DocTypeId.WITHHOLDING_TAX`)
  - `policies/`: Business rule specifications & validation engine
    - `financial_rules.py`: Math balance, VAT 7%, WHT, and Confidence scoring (`ValidationStrategyEngine`)
  - `services/`: Pure string & mapping algorithms
    - `text_normalizer.py`: Short name sanitization & Thai Buddhist Era (พ.ศ.) date parser
    - `template_evaluator.py`: JSON template record transformer (`get_nested_value`, `transform_data`)
  - `entities/`: Domain entities & aggregates
- `src/application/`: Use cases & pipeline orchestration
  - `pipeline/`: Stages 0 to 7 (`stage_0_init`, `stage_1_ingestion`, `stage_2_extraction`, `stage_3_transformation`, `stage_4_validation`, `stage_5_confirm`, `stage_6_voucher`, `stage_7_export`)
  - `usecases/`: 100% Symmetrical Stage Use Cases:
    - `initializer.py`: Stage 0 system & storage bootstrap
    - `classifier.py`: Stage 1 zero-cost prefix & multi-tenant routing
    - `extractor.py`: Stage 2 multimodal AI prompting & token math
    - `transformer.py`: Stage 3 relational database conversion
    - `validator.py`: Stage 4 multi-rule validation, confidence scoring & archiving
    - `confirmer.py`: Stage 5 review confirmation & audit stamping
    - `voucher_generator.py`: Stage 6 Canonical Journal Voucher & ERP Target Payload Generator
  - `exporters/`: Output Strategy Adapters & Destination ERP Plugin System:
    - `base.py`: Legacy File Exporter Base (`BaseOutputExporter`)
    - `express_adapter.py`: Legacy Express PV Exporter
    - `json_adapter.py`: Google Sheet & Line Items summary
    - `registry.py`: Dynamic Exporter Registry (`list_exporters`, `get_exporter`)
    - `base_target_adapter.py`: Abstract ERP Strategy Interface (`BaseTargetAdapter`)
    - `express_target_adapter.py`: Express OE Screen RPA Target Adapter (`ExpressTargetAdapter`)
    - `adapter_registry.py`: Dynamic Destination Target Registry (`TargetAdapterRegistry`)
  - `dtos/`: Pydantic V2 schemas (`settings_dto.py`, `document_dto.py`)
- `src/infrastructure/`: Technical adapters & external persistence (Organized in 3 Enterprise Pillars)
  - `database/`: 🗄️ **เสาหลักที่ 1: Database & Data Access**
    - `engine.py`: Engine, Session Pool, Dispose, Connection lifecycle
    - `models.py`: Pure SQLAlchemy 2.0 ORM Entities (`Role`, `Company`, `User`, `UserCompany`, `DocumentType`, `AIModelConfig`, `BaseEntity`, `BaseLogEntity`, `AppendOnlyAuditMixin`, `MutableAuditMixin`, `DocumentControl`, `Batch`, `BatchPage`, `Merchant`, `ExpenseReceipt`, `IntegrationMethod`, `TargetSystem`, `VoucherStatus`, `ConsolidateMode`, `ExpenseType`, `ExpenseAccountMapping`, `JournalVoucher`, `JournalVoucherItem`, etc.)
    - `schema.py`: DDL Initializer & DB Reset with Automated Table Migrations
    - `seeder.py`: Initial Master Data Seeders (Roles, AI Models, Doc Types, Statuses, Integration Methods, Target Systems, Voucher Statuses, Consolidate Modes, Expense Types, GL Mappings, Real-World Merchants Grab/SPX/Shopee, Users)
    - `repositories/`: Single-responsibility Repository layer
      - `ai_config_repo.py`: Universal AI Provider & Pricing Configs with `@ttl_cache`
      - `accounting_config_repo.py`: GL Account Mappings & Master Expense Types
      - `voucher_repo.py`: Journal Voucher CRUD, Sequential Running Numbers & Concurrency Lease Locks
      - `batch_repo.py`: Ingestion Batches & Chunk Pages
      - `document_repo.py`: DocumentControl Supertype & 15-min Leases
      - `receipt_repo.py`: ExpenseReceipt Subtype & Relational Items
      - `merchant_repo.py`: Merchant Gatekeeper & Matching
      - `company_repo.py`: Tenant Company Master CRUD & AI Config binding
      - `user_repo.py`: Enterprise RBAC, Multi-Company Mapping & Super Admin Bypass
  - `external/`: 🔌 **เสาหลักที่ 2: External Adapters & Third-party Services**
    - `ai/`: Unified GenAI Client & Dynamic Token Cost Math (`ai_service.py`, `cost_estimator.py`)
    - `pdf/`: PyMuPDF Splitting, Image Resizing (`pdf_service.py`, `image_service.py`)
    - `storage/`: Local/S3 Disk Storage Driver (`base.py`, `local_adapter.py`, `storage_manager.py`)
  - `core/`: ⚙️ **เสาหลักที่ 3: Cross-Cutting Core Utilities**
    - `constants.py`: Enums, Defaults, Status Codes, `SystemUserId`, `UserRole`, `EntityIdPrefix`
    - `user_context.py`: Universal User & Security Context Provider (`get_current_user_id`, `user_scope`, `set_current_user_id`, ContextVar)
    - `logger.py`: Universal Logging Gateway
    - `config.py`: Pure Settings Loader (Zero DB dependency)
    - `lock.py`: Pipeline Process File Lock
    - `telemetry.py`: API Call Telemetry & Audit Logs
    - `healthcheck.py`: System Readiness & Database Diagnostic Probes
    - `utils.py`: Thread-Safe `@ttl_cache`, Chunking & Tax ID Utilities
- `apps/`: Presentation & delivery mechanisms
  - `api/`: FastAPI REST endpoints & dependency injection
  - `streamlit/`: Streamlit web UI dashboard (Synced with `UserContext`)
- `configs/`: `settings.json` (Validated by `SystemSettingsModel`) & `doc_types/`
- `storage/`: `database/` (`pipeline.db`) & `companies/` (Tenant data folders)

## 2. Pipeline Workflow (Per-Batch Concurrency Isolation)
1. **Stage 0 (`init_system`)**: Validates config & initializes DB/storage.
2. **Stage 1 (`split_and_match`)**: Splits PDF to JPGs, computes SHA-256, matches merchant rules, outputs `batch_id`.
3. **Stage 2 (`extract_documents(batch_id)`)**: Multimodal AI extraction + token cost calculation for target batch.
4. **Stage 3 (`transform_to_db(batch_id)`)**: Inserts normalized records into SQLite via SQLAlchemy 2.0 for target batch.
5. **Stage 4 (`validate_documents(batch_id)`)**: Verifies financial math balance & confidence scores for target batch.
6. **Stage 5 (`confirm_receipts(batch_id)`)**: Human review confirmation & audit stamping for target batch.
7. **Stage 6 (`generate_journal_vouchers(batch_id)`)**: Canonical GL Journal Voucher generation & 50-Tawi WHT calculation.
8. **Stage 7 (`export_target_payloads(batch_id)`)**: Destination Express OE / ERP JSON formatting (`is_override_vat`) & READY sealing.
9. **Exporters (`run_export_outputs`)**: Generates legacy CSV, JSON, and CP874 Express PV files.

## 3. Database & Persistence Layer (Multi-Database Support)
- **Engines**: SQLite (Default / Dev / Edge) ⇄ PostgreSQL / MySQL (Production / Cloud)
- **Auto Schema Init**: `initialize_db_schema()` via Pure SQLAlchemy 2.0 `Base.metadata.create_all()`
- **Lifecycle, RBAC & Concurrency Architecture**:
  - **Universal UserContext & Security Context Provider (`src/infrastructure/core/user_context.py`)**: Thread-Safe & Async-Safe `contextvars` holding the active user context across Background Pipeline workers (`usr_system_auto`), Interactive Walkthroughs (`usr_system_admin`), and Streamlit / Future Login UI (`st.session_state["user_id"]`).
  - **Strict Zero-Default Policy**: All mutating functions strictly require actor parameters or resolve via `get_current_user_id()`, eliminating silent default fallbacks.
  - **Data-Driven RBAC Super Admin Bypass (`roles.is_admin`)**: Roles with `is_admin == 1` bypass tenant mapping and access all companies, while non-admin roles are strictly scoped to mapped companies in `user_companies`.
  - **4 Audit Columns (Clean State Pattern)**: Standardized `created_at`, `created_by`, `updated_at` (initial `None`), `updated_by` (initial `None`) via `AuditTrailMixin`.
  - **Lifecycle Finalization (`is_closed`)**: Atomic guard (`is_closed == 0`) seals approved/rejected documents against post-approval modifications.
  - **Airline Ticket Hold Concurrency (`is_locked`, `locked_by`, `locked_at`)**: 15-minute exclusive editing lease with heartbeat renewal and automatic expiration/release to prevent stale locks.
  - **Smart Chunk Checkpointing (`batch_pages.chunk_index`)**: Multi-page PDF extraction tracks chunk-level progress (`PENDING` ➔ `EXTRACTED` / `FAILED`), caching completed chunks and allowing instant resuming for failed segments.

## 4. Test Suite (Targeted Testing Protocol & Two-Tier Test Harness)
- **Two-Tier Test Isolation Guard**:
  - **Tier 1 (Root Guard `tests/conftest.py`)**: Session-level isolation redirecting all DB operations to temporary SQLite database, setting `TEST_ENVIRONMENT="1"` and `APP_ENV="testing"` to bypass disk logging DB sink, and autouse `auto_test_user_context_guard` for context isolation.
  - **Tier 2 (Integration Guard `tests/integration/conftest.py`)**: Package-level fixture initializing schema (`initialize_db_schema()`) and seeding master data (`seed_initial_data()`) exclusively for integration tests.
- **Environment-Aware Logging Gateway**: Bypass DB sink during testing to eliminate SQLite lock contention and maximize execution speed.
- **Targeted Test Commands**:
  - Run all tests: `pytest tests/ -v` (128 unit & integration tests, 100% Passed)
  - Run unit tests (offline & pure logic): `pytest tests/unit -v`
  - Run integration tests (DB & pipeline): `pytest tests/integration -v`
