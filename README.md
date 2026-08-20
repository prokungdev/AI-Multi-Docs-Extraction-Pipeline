# 🚀 AI Multi-Docs Extraction Pipeline

An enterprise-grade, end-to-end document processing pipeline powered by Google Gemini AI. The system ingests multi-format documents (PDF, JPG, PNG, WEBP), performs merchant template matching, page splitting, structured AI extraction, rule-based data validation, SQLite relational data transformation, and multi-format export (Accounting CSV/Excel & Express PV Voucher).

---

## ⚡ Quick Start & Installation

To set up your local development environment, follow the comprehensive [**Installation & Setup Guide**](docs/installation_guide.md).

### 1-Click Automated Setup (Windows)
```cmd
setup_env.bat
```

### Launch Web UI
```cmd
run_ui_streamlit.bat
```

---

## 🏗️ Core Architecture & Pipeline Stages

```mermaid
flowchart LR
    A[Raw Inbox Files] --> B[Step 1: Split & Match]
    B --> C[Step 2: AI Extraction]
    C --> D[Step 3: Validation & Priority]
    D --> E[Step 4: Relational DB Import]
    E --> F[Step 5: Multi-Format Exports]
```

1. **Initialization (`init`)**: Verifies system configs (`settings.json`), creates pipeline storage directory structure, and initializes SQLite tables.
2. **Split & Match (`split_match`)**: Splits multi-page PDFs into web-optimized page images (DPI 150, Max 1800px, Quality 85%) and matches merchant templates (SPX, Grab, Shopee, etc.).
3. **AI Extraction (`extract`)**: Transmits split page images to Gemini AI models for JSON extraction adhering to domain schema (`schema.json`).
4. **Validation & Post-Processing (`validate`)**: Normalizes dates (BE to AD), validates tax IDs, verifies subtotal/discount/VAT financial formulas, and assigns review priorities (`HIGH`/`MED`/`LOW`).
5. **Relational DB Import (`transform_db`)**: Transforms normalized data into SQLite relational schema (`documents`, `expense_receipts`, `receipt_items`).
6. **Multi-Format Exporters (`export`)**: Generates summary reports (Google Sheets format, Accounting Line Items, Express PV Voucher format).

---

## 📁 Repository Structure

```text
├── configs/               # System settings, merchant rules & schemas
├── docs/                  # System documentation & guides
│   └── installation_guide.md # Detailed Installation & Environment Guide
├── notebooks/             # Step-by-step walkthrough notebooks
├── src/
│   ├── core/              # Core business logic & pipeline services
│   ├── db/                # SQLite connection & ORM helpers
│   ├── exporters/         # Exporter modules (CSV, Excel, Express PV)
│   ├── ui/                # Streamlit Web UI interface
│   └── validators/        # Business rules & financial validators
├── main.py                # Pipeline CLI entry point
├── setup_env.bat          # Automated environment setup script
├── run_ui_streamlit.bat   # Streamlit Web UI launcher
└── requirements.txt       # Project dependencies
```

---

## 📖 Documentation & Guides

- 📘 [**Installation & Setup Guide**](docs/installation_guide.md)
- 🧰 [**AI Skill Kit Guide**](docs/skills_guide.md)
- 📙 [**Knowledge Base**](docs/KNOWLEDGE_BASE.md)
- 📓 [**Pipeline Walkthrough Notebook**](notebooks/01_pipeline_walkthrough.ipynb)

---

## 📜 License & Standards

All code comments, technical docstrings, and documentation follow English standard conventions, with user-facing interface labels in Thai as required.
