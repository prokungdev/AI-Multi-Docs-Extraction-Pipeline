flowchart TD
    subgraph L1["1. INGESTION & ACCESS CHANNELS"]
        UI["💻 Web UI (Streamlit / Portal)"]
        MAIL["📧 Email Ingestion"]
        DROP["📁 Drop Zone Folder"]
        CLOUD["☁️ Cloud Storage (S3/GCS)"]
    end

    subgraph L2["2. PIPELINE ORCHESTRATOR"]
        DISPATCH["⚡ Stage 1 to 5 Async Dispatcher"]
        QUEUE["📋 Task Queue & Worker Pool"]
    end

    subgraph L3["3. API GATEWAY"]
        API["🚀 FastAPI Gateway (Auth / RBAC / Rate Limit)"]
    end

    subgraph L4["4. AI EXTRACTION & RECONCILIATION ENGINE"]
        LLM["🤖 Gemini 2.5 Flash LLM (JSON Schema)"]
        MATH["∑ Mathematical Reconciler (VAT 7%)"]
        MERCH["🏪 Merchant Matching & Tax ID Resolver"]
    end

    subgraph L5["5. PERSISTENCE LAYER (SQLAlchemy 2.0)"]
        DOCS["📑 Document Header Master (Supertype)"]
        EXPENSE["🧾 Expense Receipts & Line Items (Subtype)"]
        STORAGE["🗄️ Secure Document Storage"]
    end

    subgraph L6["6. BUSINESS OUTPUT & INTEGRATION"]
        AUDIT["👁️ Human-in-the-Loop Review Screen"]
        ERP["🏢 ERP Connector & Accounting API"]
        EXPORT["📊 Excel / CSV / JSON Export"]
    end

    subgraph CCS["🛡️ CROSS-CUTTING SERVICES"]
        SEC["🔒 Security & Company Isolation"]
        COST["📈 AI Telemetry & Token Cost"]
        LOCK["🔐 Audit & Lease Locking"]
        GOV["🏛️ Data Governance & Retention"]
    end

    L1 --> L2 --> L3 --> L4 --> L5 --> L6
    CCS -.-> L2
    CCS -.-> L3
    CCS -.-> L4
    CCS -.-> L5
