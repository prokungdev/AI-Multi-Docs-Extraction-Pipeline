# 🛡️ Security & Data Privacy Guidelines

This document defines the production-grade security, data privacy, and vulnerability prevention rules for this workspace.

---

## 1. 🔒 OWASP Top 10 Safeguards
- **SQL Injection Prevention**: ALWAYS use parameterized queries or ORM models for database access. NEVER concatenate string variables directly into SQL statements.
- **Path Traversal Safeguards**: ALWAYS sanitize user-supplied file paths using `os.path.basename` or strict whitelist checks. NEVER open unvalidated arbitrary file paths.
- **Command Injection Safeguards**: Avoid dynamic shell executions (`os.system` / `subprocess(shell=True)`). Pass arguments as explicit arrays (`subprocess.run(["cmd", "arg1"])`).

---

## 2. 🙈 Personally Identifiable Information (PII) Masking
- **Logs & UI Sanitization**: Sensitive user data (e.g., Tax IDs, Phone Numbers, Credit Card Numbers, National IDs) MUST be masked before rendering in logs or debug displays (e.g. `1234xxxx5678`).
- **No Secret Leakage**: API Keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`), private keys, or passwords MUST NEVER be logged or rendered in UI stack traces.

---

## 3. 📦 Dependency & Secret Hygiene
- **Secret Management**: All secrets must be loaded dynamically via `.env` or runtime environment variables.
- **No Insecure Dependencies**: Regularly verify that third-party packages in `requirements.txt` do not contain known Critical/High CVE security vulnerabilities.
