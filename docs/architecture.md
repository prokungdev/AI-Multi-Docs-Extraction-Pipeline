# Project Architecture & Quick Map

## 1. Canonical Domain-Driven Design (DDD) Structure
- `src/domain/`: Pure business rules & domain services
  - `services/`: `classifier.py`, `transformer.py`, `post_processor.py`
  - `policies/`: Business rule specifications (`validators.py`)
  - `entities/`: Domain entities & aggregates
- `src/application/`: Use cases & pipeline orchestration
  - `pipeline/`: Stages 0 to 4 (`init`, `ingest`, `extract`, `transform`, `validate`)
  - `usecases/`: `initializer.py`, `extractor.py`
  - `dtos/`: Pydantic V2 schemas (`settings_dto.py`, `document_dto.py`)
- `src/infrastructure/`: Technical adapters & external persistence
  - `ai/`: Gemini LLM SDK client & cost estimation (`ai_service.py`, `cost_estimator.py`)
  - `pdf/`: PyMuPDF engine & Pillow image splitting (`pdf_service.py`, `image_service.py`)
  - `persistence/`: Pure SQLAlchemy 2.0 ORM (`pipeline.db`)
  - `storage/`: Multi-tenant disk path manager (`storage_manager.py`)
  - `exporters/`: Output strategy adapters (`express_adapter.py`, `json_adapter.py`, `registry.py`)
  - `common/`: Infrastructure logging, constants, config loader, healthcheck
- `apps/`: Presentation & delivery mechanisms
  - `api/`: FastAPI REST endpoints & dependency injection
  - `streamlit/`: Streamlit web UI dashboard
- `configs/`: `settings.json` (Validated by `SystemSettingsModel`) & `doc_types/`
- `storage/`: `database/` (`pipeline.db`) & `companies/` (Tenant data folders)

## 2. Pipeline Workflow
1. **Stage 0 (`init_system`)**: Validates config & initializes DB/storage.
2. **Stage 1 (`split_and_match`)**: Splits PDF to JPGs, computes SHA-256, matches merchant rules.
3. **Stage 2 (`extract_documents`)**: Multimodal AI extraction + token cost calculation.
4. **Stage 3 (`transform_to_db`)**: Inserts normalized records into SQLite via SQLAlchemy 2.0.
5. **Stage 4 (`validate_documents`)**: Verifies financial math balance & confidence scores.
6. **Exporters (`run_export_outputs`)**: Generates CSV, JSON, and CP874 Express PV files.

## 3. Database Models (SQLite — `storage/database/pipeline.db`)
- `companies`, `merchants`: Master entities & rules
- `processed_batches`, `document_pages`: Raw ingestion tracking
- `documents`, `expense_receipts`, `expense_receipt_items`: Extracted transactional data
- `api_call_logs`, `application_logs`: Observability & telemetry

## 4. Test Suite (Modern Pytest + DDD Layering)
- Run all tests: `pytest tests/ -v` (85 unit & integration tests)
- Run unit tests (offline & in-memory): `pytest tests/unit -v`
- Run integration tests (DB & pipeline): `pytest tests/integration -v`
