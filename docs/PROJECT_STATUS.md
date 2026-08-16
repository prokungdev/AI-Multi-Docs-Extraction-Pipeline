# AI-Multi-Docs-Extraction-Pipeline — Project Status

> **Last Updated**: 2026-08-16
> **Pipeline Version**: 1.0 (Development)
> **Active Domain**: `expense_receipt`
> **AI Provider**: Google Gemini (`gemini-3.5-flash`)

---

## Overview

An end-to-end automated pipeline that extracts structured data from multi-page PDF receipts using a Generative AI model (Gemini). The pipeline minimizes API usage by batching up to 50 pages per request, then splits the array response back into individual per-page JSON files.

---

## Architecture

```
01_raw_inbox/           → Raw PDF files organized by source folder
        ↓
split_and_match.py      → Step 2: Split PDFs → PNG pages, match source, register to DB
        ↓
02_split_pages/         → Individual PNG images per page
        ↓
extract_data.py         → Step 3: Batch pages → Gemini API → Parse array response
        ↓
03_processing_queue/    → Per-page JSON files, organized by source sub-folder
        ↓
transform_outputs.py    → Step 4: Merge & transform JSONs → Final output files
        ↓
outputs/                → Final structured output (CSV / Excel / JSON)
        ↓
main.py (Streamlit UI)  → Step 5: View & manage results via web dashboard
```

---

## Database Schema (SQLite — `pipeline_storage/pipeline.db`)

| # | Table | Description |
|---|-------|-------------|
| 1 | `document_domains` | Registered AI extraction domains (e.g. `expense_receipt`) |
| 2 | `document_sources` | Sub-sources per domain (e.g. `grab_thailand`, `shopee_thailand`) |
| 3 | `document_statuses` | Lookup table for document lifecycle statuses |
| 4 | `processed_batches` | One row per source PDF file processed in Step 2 |
| 5 | `document_pages` | One row per split PNG page, linked to a batch |
| 6 | `documents` | One row per extracted document (result of Step 3) |
| 7 | `api_credentials` | Gemini/OpenAI API keys with rotation and health tracking |
| 8 | `api_call_logs` | One row per Gemini API call, stores tokens, latency, raw response |
| 9 | `application_logs` | All application-level log messages (INFO, WARNING, ERROR) |

---

## Completed Features

### Step 1 — System Initialization (`init_system.py`)
- Validates `settings.json` and all domain configs
- Initializes all SQLite tables (schema + seed data)
- Ensures all pipeline storage directories exist

### Step 2 — PDF Split & Match (`split_and_match.py`)
- Detects PDF source from folder name (`01_raw_inbox/{source}/`)
- Splits each PDF into individual PNG images via `pymupdf`
- Registers batch (`processed_batches`) and all pages (`document_pages`) to SQLite
- Supports AI-fallback source matching when folder name is ambiguous

### Step 3 — AI Data Extraction (`extract_data.py`)
- Loads pending batches from SQLite
- Groups pages by batch, slices into chunks of max 50 images
- Sends each chunk to Gemini API with a dynamic array-wrapped schema
  - Gemini returns {"extracted_documents": [...]} — one item per page
  - Each item includes logical_page_number for accurate page mapping
- Maps each result back to the correct document_pages DB record
- Saves individual JSON files to 03_processing_queue/{source}/
- Records one row per document in documents table (status = PROCESSED)
- API Request Minimization: 93 pages → 3 API calls (97% reduction)

### Step 4 — Transform Outputs (`transform_outputs.py`)
- Reads all JSON files from 03_processing_queue/
- Merges and transforms into final output formats

### Step 5 — Streamlit UI (`main.py`)
- Dashboard to browse extracted documents
- View per-document JSON data
- Monitor pipeline status and API logs

### Logging System
- Text log: Daily rotating log file → logs/logs_YYYYMMDD.txt
- Console: Colorized terminal output via Loguru
- SQLite api_call_logs: Input/output tokens, latency, raw API response string
- SQLite application_logs: All INFO/WARNING/ERROR messages from every module

### API Credential Management
- Multiple API keys supported with round-robin rotation
- Automatic deactivation after 3 consecutive failures
- Health tracking via error_count and is_active flags

---

## Configuration

### `configs/settings.json`

| Key | Value | Description |
|-----|-------|-------------|
| `active_domains` | `["expense_receipt"]` | Domains to process |
| `max_images_per_request` | `50` | Max pages per Gemini API call |
| `ai_provider.active_provider` | `gemini` | Active AI backend |
| `ai_provider.gemini.model_name` | `gemini-3.5-flash` | Gemini model |
| `logging.rotation` | `00:00` | Daily log rotation at midnight |
| `logging.retention` | `30 days` | Log file retention period |

### Domain: `expense_receipt`

| Source | Folder | Status |
|--------|--------|--------|
| Grab Thailand | `grab_thailand/` | Active |
| Shopee Thailand | `shopee_thailand/` | Active |
| SPX Express | `spx_express/` | Active |
| Default (AI Fallback) | `_default/` | Active |

---

## Key Source Files

| File | Role |
|------|------|
| `init_system.py` | Step 1: System & DB initialization |
| `split_and_match.py` | Step 2: PDF split, source matching, DB registration |
| `extract_data.py` | Step 3: AI batch extraction runner |
| `transform_outputs.py` | Step 4: Output transformation |
| `main.py` | Step 5: Streamlit UI |
| `src/core/db.py` | All SQLite CRUD operations |
| `src/core/extractor.py` | Gemini API calls, array schema wrapping, response parsing |
| `src/core/logger.py` | Loguru setup: console + file + SQLite sinks |
| `src/core/pdf_splitter.py` | PDF to PNG conversion |
| `src/core/source_matcher.py` | Source detection logic |
| `src/core/transformer.py` | JSON to output format transformation |
| `src/core/config_loader.py` | Config & schema loading |

---

## Last E2E Test Results

| Metric | Result |
|--------|--------|
| Total pages processed | 93 pages |
| Sources | grab_thailand (30), shopee_thailand (33), spx_express (30) |
| API calls made | 3 (1 per source batch) |
| API calls saved | 90 (97% reduction) |
| Documents saved to DB | 93 rows (PROCESSED) |
| JSON files created | 93 files in 03_processing_queue/{source}/ |
| Application logs captured | Text file + SQLite application_logs |
| Raw API response stored | SQLite api_call_logs.raw_response |
| Avg input tokens / call | ~34,484 tokens |
| Avg output tokens / call | ~10,361 tokens |

---

## Pending / Next Steps

| # | Task | Status |
|---|------|--------|
| 1 | Run full E2E pipeline end-to-end with extract_data.py and verify all 9 tables | Pending user approval |
| 2 | Verify Streamlit UI displays 93 documents correctly | Pending |
| 3 | Add unit tests for application_logs DB sink in logger.py | Planned |
| 4 | Add support for additional domains beyond expense_receipt | Future |
| 5 | Add Streamlit page for application_logs monitoring dashboard | Future |

---

## How to Run

```bat
REM Step 1 — Initialize system (first time only)
Run_01_Init.bat

REM Step 2 — Split PDFs and register pages
Run_02_Split_and_Match.bat

REM Step 3 — Extract data via Gemini AI
Run_03_Extract_Data.bat

REM Step 4 — Transform outputs to final format
Run_04_Transform_Outputs.bat

REM Step 5 — Start Streamlit dashboard
Run_05_Run_UI.bat
```

Prerequisite: Copy .env.example to .env and fill in GEMINI_API_KEY before running Step 3.
