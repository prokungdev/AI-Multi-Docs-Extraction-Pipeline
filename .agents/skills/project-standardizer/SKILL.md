---
name: project-standardizer
description: >-
  Standardizes repository layout, setup scripts, environment configuration, git hygiene (including .githooks),
  and AI-Human collaboration guidelines. Use when bootstrapping a new codebase or auditing an existing project structure.
---

# 🏗️ Software Development Project Standardization Skill

This skill defines the enterprise-grade repository standard for software development projects, optimized for **Human + AI Pair Programming**.

---

## 📐 1. Standard Directory Layout Specification

Every repository conforming to this standard MUST organize its root structure as follows:

```text
my-project/
├── .agents/                       # AI Agent workspace rules & skills (tracked in Git)
│   ├── rules/                     # Team coding guidelines & architectural constraints
│   └── skills/                    # Reusable operational runbooks & skills
├── .githooks/                     # Team-wide Git hooks (pre-commit, pre-push)
├── apps/                          # Presentation & delivery layer (API, Web UI, Mobile)
│   ├── api/                       # REST API (e.g. FastAPI / Express)
│   └── web/                       # Web interface (e.g. Streamlit / React)
├── configs/                       # Application settings, environment schemas, business rules
├── docs/                          # System documentation, guides, & architecture diagrams
│   └── installation_guide.md      # Detailed installation & setup guide
├── scripts/                       # Maintenance, migration, & automation scripts
├── src/                           # Canonical Domain-Driven Design (DDD) Core
│   ├── domain/                    # Pure business entities, policies, and domain services
│   ├── application/               # Use cases, pipeline stages, and DTOs
│   └── infrastructure/            # Technical adapters (3 Pillars: database/, external/, core/)
├── tests/                         # Automated test suite (unit, integration, e2e)
├── .env.example                   # Environment variable template (NO secrets)
├── .gitignore                     # Git exclusion rules (.venv, .env, build outputs, logs)
├── GEMINI.md / AGENTS.md          # Primary AI Agent instructions & coding standards
├── README.md                      # Project landing page & quick start entry point
├── setup_env.bat / setup_env.sh   # 1-Click automated environment setup script
└── requirements.txt / package.json# Dependency manifest
```

---

## 📜 2. Mandatory File Requirements & Templates

### A. Environment Setup Script (`setup_env.bat` / `setup_env.sh`)
Must provide a 1-click automated setup routine that:
1. Creates Python virtual environment (`.venv`) or Node dependencies if missing.
2. Installs/Upgrades dependencies from `requirements.txt` / `package.json`.
3. Copies `.env.example` to `.env` if `.env` does not exist.
4. Configures Git to use version-controlled hooks: `git config core.hooksPath .githooks`.
5. Runs system initialization or migrations.

### B. Version-Controlled Git Hooks (`.githooks/pre-commit`)
Must provide a `pre-commit` shell script that checks:
- **Secret Leak Prevention**: Blocks staging files containing hardcoded API keys or uncommitted `.env` files.
- **Syntax Check**: Validates Python / JavaScript syntax before allowing commits.

```bash
#!/bin/sh
# .githooks/pre-commit: Automated Git Pre-commit Quality Gate

echo "[Git Hook] Running pre-commit checks..."

# 1. Prevent staging .env files with secrets
if git diff --cached --name-only | grep -E "^.env$"; then
    echo "[ERROR] Attempting to commit .env file. Please remove .env from staging!"
    exit 1
fi

# 2. Check for potential hardcoded secrets/API keys
if git diff --cached | grep -iE "PROVIDER_API_KEY=AIza|SECRET_KEY=sk-"; then
    echo "[ERROR] Hardcoded API Key detected in staged diff! Commit aborted."
    exit 1
fi

echo "[Git Hook] Pre-commit checks passed successfully!"
exit 0
```

### C. Primary AI Agent Instructions (`AGENTS.md` / `GEMINI.md`)
Must define:
1. **Code Comment Language**: English for all code docstrings, comments, and technical docs.
2. **Approval Requirements**: AI MUST present an Implementation Plan and wait for explicit user approval before modifying code files.
3. **Git Synchronization Pre-Check**: AI MUST verify `git status` / `git fetch` and prompt user to `git pull origin main` before presenting plans.

### D. Documentation (`README.md` & `docs/installation_guide.md`)
- `README.md` MUST serve as the project landing page with an architecture overview and relative links to `docs/installation_guide.md`.
- `docs/installation_guide.md` MUST contain both 1-Click Automated Setup and Manual Setup instructions.
- All internal markdown documentation MUST use relative links instead of local absolute `file:///` URIs.

### E. Modular Workspace Rules (`.agents/rules/coding-standards.md`)
- Must establish universal, language-agnostic coding standards (English docstrings/comments, secret safety, clean code, semantic commit rules).

### F. System Health Check Routine (Recommended for Production-Grade)
- Recommended to provide a zero-cost 1-Click health check entry point (e.g., `python -m app.healthcheck` or a dedicated healthcheck CLI command) to validate DB connectivity, dynamically resolve environment credential keys from configuration schemas, and execute storage write permission probes prior to accepting workloads.

---

## 🤖 3. AI Execution & Audit Workflow

When triggered to **audit** or **standardize** a repository, the AI Agent MUST follow these steps:

1. **Scan Workspace Structure**:
   Check for the existence of `src/`, `tests/`, `docs/`, `.agents/`, `.githooks/`, `.gitignore`, `.env.example`, `setup_env.bat`, `GEMINI.md`, and `README.md`.
2. **Identify Missing Components**:
   List all missing directories, missing configuration files, or non-compliant link references.
3. **Create Implementation Plan**:
   Generate an `implementation_plan.md` artifact detailing the proposed changes and wait for user approval.
4. **Execute & Verify**:
   - Create missing directories and files.
   - Configure `.githooks/pre-commit`.
   - Update `setup_env.bat` with `git config core.hooksPath .githooks`.
   - Verify setup by testing script execution and link validity.
