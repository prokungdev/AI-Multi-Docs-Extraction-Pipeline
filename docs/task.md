# Task Checklist - AI-Multi-Docs-Extraction-Pipeline

## Phase 1: Project Setup & Configs
- [x] Create staging storage folders under `pipeline_storage/` (Nested under domain folders)
- [x] Create `requirements.txt` with required dependencies
- [x] Create `.env.example` file
- [x] Create configs/domains/expense_receipt/schema.json
- [x] Create configs/settings.json for central configuration
- [x] Create merchant configs (rules.json, prompt.txt) under `sources/`
  - [x] `_default`
  - [x] `spx_express`
  - [x] `shopee_thailand`
  - [x] `grab_thailand`
- [x] Create output conversion configs under `outputs/`
  - [x] `google_sheet_summary.json`
  - [x] `accounting_line_items.json`

## Phase 2: Core Processing Engine
- [x] Develop `src/core/pdf_splitter.py` (PyMuPDF-based page splitter)
- [x] Develop `src/core/source_matcher.py` (Source classifier and rules matcher)
- [x] Develop `src/core/extractor.py` (Gemini SDK structured extractor)
- [x] Develop `src/core/transformer.py` (Dot-notation data transformer)

## Phase 3: CLI & E2E Testing
- [x] Create `main.py` CLI script
- [x] Run End-to-End tests with mock receipts

## Phase 4: Streamlit UI
- [x] Develop `src/ui/app.py` Side-by-side Review UI

## Phase 5: System Initializer & Config Validator
- [x] Develop `src/core/initializer.py` (Validation functions and directory creator)
- [x] Develop `init_system.py` (CLI wrapper script)
- [x] Modify `main.py` to run validation on startup
- [x] Modify `src/ui/app.py` to run validation on startup and show diagnostics

## Phase 6: Config-Driven Logging & Log Viewer UI
- [x] Modify configs/settings.json to include logging block
- [x] Add loguru to requirements.txt and install it
- [x] Modify src/core/initializer.py to validate logging configs
- [x] Develop src/core/logger.py (Loguru config setup)
- [x] Modify core modules & main.py to use Loguru instead of print()
- [x] Modify src/ui/app.py to add the Log Expander & Download console
- [x] Support systematic naming ({domain}_{source}_{doc_no}_{seq/page_no})
- [x] Support configurable split archiving (pdf, png, jpg)

## Phase 7: Flat Staging Inbox & Local-Only Source Matching
- [x] Modify configs/settings.json to flat pipeline folders
- [x] Modify src/core/initializer.py to auto-create staging subfolders
- [x] Modify src/core/source_matcher.py to disable AI vision fallback
- [x] Modify main.py to handle parent vs subfolder staging flow
- [x] Modify src/ui/app.py to handle parent vs subfolder staging flow
- [x] Verify using SPXExpress_202606_000008.pdf test flow

## Phase 8: AI Fallback Source Matching
- [x] Modify configs/settings.json to add use_ai_fallback_matching config
- [x] Modify src/core/initializer.py to validate use_ai_fallback_matching config
- [x] Modify src/core/source_matcher.py to conditionally enable first-page AI Vision fallback
- [x] Verify using SPXExpress_202606_000008.pdf E2E match flow

## Phase 9: Centralized SQLite Database Integration
- [x] Develop src/core/database.py SQLite helper module
- [x] Modify src/core/initializer.py to initialize sqlite3 database and table
- [x] Modify main.py to compute SHA-256 and validate duplicates
- [x] Modify src/ui/app.py to compute SHA-256, validate duplicates, and update status
- [x] Verify duplicate blocking using E2E script
