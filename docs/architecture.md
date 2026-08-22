# Project Architecture & Quick Map

## 1. Directory Structure
- `src/core/`:
  - `storage_manager.py`: Central path resolver (`storage/companies/{code}/{domain}/`)
  - `ai_service.py`: LLM client (GenAI SDK, retry backoff, cost estimator)
  - `constants.py`: Centralized static constants (Zero magic strings)
  - `pipeline/`: Stages 0 to 4 (`init` ➔ `ingest` ➔ `extract` ➔ `transform` ➔ `validate`)
  - `db/`: Pure SQLAlchemy 2.0 ORM (`pipeline.db`) + FastAPI `get_db_session_dep`
  - `exporters/`: Strategy pattern (`json_adapter`, `express_adapter`, `registry`)
- `apps/`: `api/` (FastAPI endpoints) & `ui/` (Streamlit dashboard)
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

## 4. Test Suite
- Run all tests: `python -m unittest discover tests -v` (42 tests, isolated DB cleanup)
