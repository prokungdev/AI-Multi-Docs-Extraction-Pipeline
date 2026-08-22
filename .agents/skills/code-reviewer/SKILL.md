---
name: code-reviewer
description: >-
  Audits code quality, identifies logic bugs, unhandled edge cases, performance bottlenecks, and security vulnerabilities.
  Integrates the full 7-skill ecosystem (database-architect, python-enterprise-stack, security-auditor,
  refactoring-expert, test-suite-generator, documentation-generator, project-standardizer) into structured Code Review Reports.
---

# 🔍 Code Reviewer Skill

This skill guides the AI Agent to perform strict, automated, and comprehensive peer reviews on source code files, modules, or git diffs against enterprise software quality standards across all specialized project skills.

---

## 🔗 1. Referenced Skill Dependencies (7-Skill Ecosystem)

When this skill is invoked, the AI Agent MUST read and strictly enforce standards from the following reference skills:

1. **`database-architect`**:
   - Enforces Plural `snake_case` table names, standardized column names (`status_code`, `created_at`, `is_` booleans).
   - Enforces Zero-Tolerance SQLAlchemy 2.0 ORM policy (`with get_db_session() as session:`, Entity Models).
   - Enforces explicit foreign keys, indexes, and cascade delete rules.
2. **`python-enterprise-stack`**:
   - Enforces Pydantic v2 schema validations, type hints, structured Dual Logging (`loguru`), and explicit exception handling.
3. **`security-auditor`**:
   - Enforces secret safety (no hardcoded keys), OWASP Top 10 prevention, SQL injection safety, and path sanitization.
4. **`refactoring-expert`**:
   - Enforces SOLID principles, DRY (Don't Repeat Yourself), and decoupled modular architecture between Core Engine, UI, and API.
5. **`test-suite-generator`**:
   - Enforces testability, realistic decoupled mock data, boundary edge-case test coverage, and 100% test pass rate.
6. **`documentation-generator`**:
   - Enforces **English-only docstrings/comments**, **Model-Agnostic** abstractions (no hardcoded model versions), **Vendor-Agnostic** examples (no hardcoded brand names), and architectural accuracy.
7. **`project-standardizer`**:
   - Enforces repository layout, clean folder structures (`doc_types/`, `storage/`), and avoidance of stray/junk files.

---

## 🎯 2. Mandatory Pre-Review Static Scan Checklist

Before writing any Review Report or assigning quality scores, the AI Agent **MUST execute static grep searches** across the target codebase to detect anti-patterns with **Zero Tolerance**:

| Check Target | Search Pattern | Related Skill | Strict Rule & Violation Penalty |
| :--- | :--- | :--- | :--- |
| **Raw SQL & Cursor Usage** | `cursor.execute`, `sqlite3.connect`, `get_db_connection` in `src/` | `database-architect` | **🚨 CRITICAL (Auto-FAIL DB Layer)**: Absolutely NO raw SQL or cursor manipulation allowed in application/master logic. Every DB interaction MUST use SQLAlchemy ORM (`get_db_session()`, Entity Models). |
| **Bare Print Statements** | `print(` in `src/` | `python-enterprise-stack` | **⚠️ WARNING**: Must use structured `loguru.logger` instead of stdout prints. |
| **Hardcoded Secrets** | `AIzaSy`, `sk-`, `password =`, `api_key = "..."` | `security-auditor` | **🚨 CRITICAL**: All secrets must be loaded dynamically via `.env` / `os.getenv()`. |
| **Non-English Code Artifacts** | Thai/Regional non-ASCII in comments or docstrings | `documentation-generator` | **⚠️ WARNING**: Comments, docstrings, and debug logs must be in **English only**. |
| **Hardcoded Models & Brand Names** | Specific model versions (e.g. "Gemini 2.5 Flash") or vendor names (e.g. "grab_thailand") in comments/docstrings | `documentation-generator` | **⚠️ WARNING**: Docstrings and comments must be model-agnostic and vendor-agnostic, using generic abstractions and matching the current system architecture. |
| **Legacy Table/Column Names** | `_d` suffix, `merchant_master`, `timestamp` in tables | `database-architect` | **⚠️ WARNING**: Must use standardized Plural table names (`merchants`, `expense_receipt_items`) and consistent columns (`created_at`, `status_code`). |

---

## 📐 3. Review Audit Dimensions

The AI Agent MUST evaluate the target code across the following dimensions without leniency or high-level assumptions:

1. **💾 Database & ORM Compliance (`database-architect`)**:
   - **Zero Tolerance Policy**: Reject any raw SQL or manual cursor queries.
   - Confirm all DB operations use SQLAlchemy ORM models and `with get_db_session() as session:` context manager.
   - Confirm table names use Plural `snake_case` without legacy abbreviations.
2. **🛡️ Security & Secret Safety (`security-auditor`)**:
   - Check for hardcoded API keys, secrets, passwords, or tokens.
   - Verify input sanitization and prevention of injection vulnerabilities.
3. **🐛 Logic Correctness & Edge Cases**:
   - Check for null pointers, undefined variable references, off-by-one errors, and boundary conditions.
   - Verify that exception handling is explicit and does NOT swallow errors silently (`except: pass`).
4. **⚡ Performance & Memory Efficiency (`refactoring-expert`)**:
   - Identify redundant DB queries, N+1 query patterns, memory leaks, or missing fast-path bypasses.
5. **🧪 Testability & Clean Architecture (`test-suite-generator`)**:
   - Verify decoupling between UI (`apps/`), API (`apps/api/`), and Core Engine (`src/core/`).
   - Confirm test suite passes 100% with no skipped critical paths.
6. **📝 Logging & Observability Audit (`python-enterprise-stack`)**:
   - Verify structured logger usage (`loguru`) instead of bare `print()`.
   - Confirm exception blocks explicitly log errors with stack traces (`logger.error()`).
7. **📐 Documentation Hygiene & Standards (`documentation-generator`)**:
   - Confirm docstrings and comments are in **English only**.
   - Confirm docstrings and comments **do NOT hardcode specific AI models** (e.g. "Gemini 2.5 Flash") or **vendor brand names** (e.g. "grab_thailand").
   - Confirm docstrings **accurately reflect the current system architecture**.
8. **🏷️ Enum & Constants Compliance**:
   - Confirm domain statuses, priority levels, and category codes use strongly-typed `Enum` classes instead of inline hardcoded string literals.

---

## 🤖 4. Execution Workflow

1. **Perform Automated Static Scan**:
   - Run grep searches for forbidden patterns (`cursor.execute`, `print(`, hardcoded keys, hardcoded model/vendor names in docstrings).
2. **Perform Multi-Dimensional Audit**:
   - Evaluate code against all audit dimensions across the 7 skills above.
3. **Zero-Leniency Grading**:
   - If any violation exists, the dimension **MUST be marked as FAILED / REQUIRES REFACTOR**, never marked as "PASSED" or "Hybrid".
4. **Generate Code Review Report**:
   - Present findings organized by severity:
     - 🚨 **Critical**: Raw SQL usage, security risks, unhandled crashes, or severe data loss bugs.
     - ⚠️ **Warning**: Outdated/coupled docstrings, code smells, missing error handling, missing logs, bare print statements.
     - 💡 **Suggestion**: Enum refactoring, dynamic config mapping, clean code tips.
5. **Provide Actionable Refactor Diffs**:
   - Include code diff snippets showing exact recommended fixes.
