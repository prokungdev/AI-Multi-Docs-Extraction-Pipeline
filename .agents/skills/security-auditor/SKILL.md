---
name: security-auditor
description: >-
  Audits workspace source code, configuration files, and dependencies for security vulnerabilities
  (OWASP Top 10, secret leaks, SQL injection, insecure dependencies).
---

# 🛡️ Security Auditor Skill

This skill guides the AI Agent to perform security static analysis, secret scanning, and dependency vulnerability audits across the repository.

---

## 🎯 1. Security Audit Dimensions

1. **Secret & Credential Scanning**:
   - Check for hardcoded API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, AWS keys), private keys, or passwords.
   - Verify `.env` is listed in `.gitignore`.
2. **Injection Vulnerabilities**:
   - Check for un-parameterized SQL queries (SQL Injection).
   - Check for un-sanitized shell execution commands (`os.system`, `subprocess` with `shell=True`).
3. **Insecure Data Handling & Storage**:
   - Verify sensitive user data or API keys are not written to debug log files.
4. **Dependency Vulnerabilities**:
   - Inspect `requirements.txt` / `package.json` for known vulnerable package versions.

---

## 🤖 2. Execution Workflow

1. **Scan Source Code & Configs**:
   - Search for sensitive patterns, un-parameterized queries, and dynamic command executions.
2. **Generate Security Vulnerability Report**:
   - Categorize findings by risk level:
     - 🚨 **HIGH**: Exposed credentials, SQL Injection, Remote Code Execution risks.
     - ⚠️ **MEDIUM**: Missing input validation, insecure logging, outdated dependencies.
     - ℹ️ **LOW**: Minor security header or configuration recommendations.
3. **Propose Remediation Plan**:
   - Provide concrete fix recommendations (e.g. parameterizing SQL queries, moving keys to `.env`).
