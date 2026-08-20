---
name: documentation-generator
description: >-
  Automatically scans codebase modules, database models, and system architecture to generate or update
  comprehensive, standardized technical documentation in docs/ (architecture.md, database_schema.md, installation_guide.md, README.md).
---

# 📝 Technical Documentation Generator Skill

This skill guides the AI Agent to inspect codebase modules, database schemas, and configuration parameters to generate or maintain enterprise-grade software documentation.

---

## 🎯 1. Target Documentation Suite

When executed, this skill manages four core documentation artifacts inside the repository:

### A. System Architecture (`docs/architecture.md`)
Must contain:
- **System Overview**: Business goals, high-level capabilities, and target user domains.
- **Component Diagram**: A clear `mermaid` flowchart rendering interactions between input processing, core pipeline stages, database storage, and exporters.
- **Pipeline Stage Breakdown**: Detailed descriptions of each processing stage (`init`, `split_match`, `extract`, `validate`, `transform_db`, `export`).
- **Module Responsibilities**: Summary of services under `src/core/`, `src/db/`, `src/validators/`, `src/exporters/`, and `src/ui/`.

### B. Database Schema & Data Models (`docs/database_schema.md`)
Must contain:
- **ER Diagram**: A `mermaid` entity relationship diagram depicting primary keys, foreign key constraints, and table relationships.
- **Table Specifications**: Detailed Markdown tables enumerating column names, data types, constraints (NOT NULL, UNIQUE), and business meanings for:
  - Master documents table (`documents`)
  - Domain receipt table (`expense_receipts`)
  - Line items table (`receipt_items`)
- **Indexing & Queries**: Key indices and sample SQL queries used in the application.

### C. Installation & Environment Guide (`docs/installation_guide.md`)
Must contain:
- **Prerequisites**: Required OS, Python version, Git, and API Keys.
- **1-Click Automated Setup**: Instructions for running `setup_env.bat` (which configures `.venv`, pip packages, `.env`, `.githooks`, and DB schema).
- **Manual Setup Steps**: CLI commands for manual virtualenv activation, dependency installation, and environment configuration.
- **Troubleshooting**: Diagnostic steps for common issues (`loguru` missing, PowerShell ExecutionPolicy, API key setup).

### D. Root Landing Page (`README.md`)
Must contain:
- Project badges, high-level summary, and architecture diagram.
- Quick start instructions linking to `docs/installation_guide.md`.
- Relative Markdown links pointing to all docs in `docs/`.

---

## 📏 2. Documentation Guidelines & Hygiene

1. **Relative Links Only**: ALL markdown file links MUST use clean relative links (e.g. `docs/installation_guide.md` or `../notebooks/01_pipeline_walkthrough.ipynb`). NEVER use local absolute `file:///` URLs.
2. **Valid Mermaid Diagrams**: Quote labels containing special characters and ensure diagram syntax compiles cleanly.
3. **Synchronization with Codebase**: Always verify code imports, function signatures, and SQLite table definitions against active source files before writing documentation.

---

## 🤖 3. AI Execution Steps

When triggered to **generate** or **update** project documentation, follow these steps:

1. **Inspect Codebase**:
   - Inspect `src/core/` for pipeline stages.
   - Inspect `src/db/` for SQLite table definitions.
   - Inspect `configs/` for domain schemas and rules.
2. **Audit Existing Docs**:
   - Check if `docs/architecture.md`, `docs/database_schema.md`, `docs/installation_guide.md`, and `README.md` exist and are up to date.
3. **Present Implementation Plan**:
   - List missing or outdated documentation files and present an `implementation_plan.md` artifact to the user.
4. **Generate & Update Docs**:
   - Write/Update the target markdown documentation files using `write_to_file`.
   - Verify that all internal links are relative and all mermaid diagrams render cleanly.
