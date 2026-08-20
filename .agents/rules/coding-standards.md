# 🛠️ Universal Software Development & Coding Standards

This document defines the language-agnostic coding standards and AI-Human collaboration guidelines for software projects in this workspace.

---

## 1. 🌐 Language & Documentation Rules
- **Technical Comments & Docstrings**: Code comments, function docstrings, class explanations, and technical docs MUST be written in **English**.
- **Error Messages & Logs**: Log statements and user error messages MUST be clear, descriptive, and actionable.

---

## 2. 🔤 Universal Naming Conventions
- **Meaningful Names**: Use self-explanatory variable, function, and class names. Avoid single-letter identifiers (e.g. `x`, `temp`, `data1`).
- **English Identifiers**: All code symbols (variables, methods, classes, types) MUST use English words only.
- **Language-Specific Casing Standards**:
  - Python / Rust / Ruby: `snake_case` for variables, functions, and modules.
  - JavaScript / TypeScript / Java / Go: `camelCase` for variables and functions.
  - All Languages: `PascalCase` for Classes, Interfaces, Structs, Enums, and Types.

---

## 3. 🛡️ Security & Secret Management
- **No Hardcoded Secrets**: NEVER commit API keys, passwords, private keys, or tokens in source code files.
- **Environment Variables**: Load secrets dynamically via `.env` files or runtime environment managers.
- **Git Exclusion**: Verify `.env` and credential files are explicitly ignored in `.gitignore`.

---

## 4. ⚡ Clean Code & Error Handling
- **Single Responsibility Principle (SRP)**: Each function/method should fulfill a single, well-defined task.
- **Explicit Error Handling**: NEVER swallow exceptions with empty catch/except blocks. Always log or re-throw errors explicitly.
- **No Unintended Side Effects**: Keep functions pure where possible and avoid mutating global application state unnecessarily.

---

## 5. 🧪 Automated Testing Standards
- **Test-Driven / Test-Accompanied Development**: New business logic or core pipeline modules MUST be covered by unit or integration tests.
- **Deterministic & Independent**: Automated tests must be reproducible and isolated from external side effects.

---

## 6. 🤖 AI & Human Collaboration Governance
- **Implementation Plan Approval**: AI MUST present a detailed `implementation_plan.md` and obtain explicit user approval before modifying code files.
- **Git Synchronization Pre-Check**: AI MUST verify `git status` / `git fetch` and prompt the user to `git pull origin main` before presenting plans.
- **Preserve Existing Documentation**: Maintain unrelated existing docstrings, comments, and architectural structures intact.

---

## 7. 📦 Git & Commit Standards
- **Atomic Commits**: Keep commits logical, atomic, and functional.
- **Semantic Commit Messages**: Use standard commit prefixes (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).

---

## 8. 📝 Standard Logging & Observability Guidelines
- **Structured Logging**: Use a structured logging library (e.g. `loguru` in Python, `winston` in JS/TS, `zap` in Go). NEVER use bare `print()` or `console.log()` statements in production code.
- **Log Levels Standards**:
  - `DEBUG`: Internal function execution details, payload shapes, and variable state inspection.
  - `INFO`: Key business milestones and status transitions (e.g. `Batch processing started`, `Document transformed successfully`).
  - `WARNING`: Recoverable non-fatal events (e.g. API retry attempts, fallback default parameters used).
  - `ERROR`: Unhandled or caught exceptions causing operational failures, accompanied by stack traces and execution context.
- **No Sensitive Logs**: NEVER write passwords, tokens, API keys, or personally identifiable information (PII) into log files.

---

## 9. 🩺 System Health & Readiness Guidelines (Recommended for Production)
- **Zero-Cost Startup Probe**: Recommended to implement a startup or entry-guard Health Check that validates local environment variables, DB connectivity, and storage folder permissions prior to processing workloads.
- **No LLM Token Waste**: Health checks for external AI APIs MUST perform zero-cost local validation or lightweight metadata checks without generating LLM response tokens.
