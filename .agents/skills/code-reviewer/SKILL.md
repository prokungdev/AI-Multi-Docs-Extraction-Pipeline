---
name: code-reviewer
description: >-
  Audits code quality, identifies logic bugs, unhandled edge cases, performance bottlenecks, and security vulnerabilities.
  Integrates the full skill ecosystem (database-architect, python-enterprise-stack, security-auditor,
  refactoring-expert, test-suite-generator, documentation-generator, project-standardizer) into structured Code Review Reports.
---

# 🔍 Code Reviewer Skill

This skill guides the AI Agent to perform strict, automated, and comprehensive peer reviews on source code files, modules, or git diffs against enterprise software quality standards across all specialized project skills.

---

## 🔗 1. Referenced Skill Dependencies

When this skill is invoked, the AI Agent MUST read and strictly enforce standards from the following reference skills:

1. **`database-architect`**:
   - Enforces Plural `snake_case` table names, standardized column names (`status_code`, `created_at`, `is_` booleans).
   - Enforces Pure SQLAlchemy 2.0 ORM policy (`select()`, `scalars()`, Entity Models). Rejects legacy `session.query()`.
   - Enforces explicit foreign keys, indexes, and cascade delete rules.
2. **`python-enterprise-stack`**:
   - Enforces Pydantic v2 schema validations, type hints, structured Dual Logging (`loguru`), and explicit exception handling.
   - Enforces **Fail-Fast Configuration**: Flags silent fallback defaults for configuration parameters defined in schemas.
   - Enforces **Centralized Constants**: Flags magic strings/numbers scattered outside constants files.
   - Enforces **FastAPI Dependency Injection**: Verifies transactional session lifecycle via `Depends(get_db_session)`.
3. **`security-auditor`**:
   - Enforces secret safety (no hardcoded keys), OWASP Top 10 prevention, SQL injection safety, and path sanitization.
4. **`refactoring-expert`**:
   - Enforces SOLID principles, DRY (Don't Repeat Yourself), Strategy Pattern for polymorphic exporters/processors, and resilient API client wrappers with exponential backoff.
5. **`test-suite-generator`**:
   - Enforces testability, decoupled mock data, boundary edge-case test coverage, Windows OS file lock teardown, and 100% test pass rate.
6. **`documentation-generator`**:
   - Enforces **English-only docstrings/comments**, **Model-Agnostic** abstractions (no hardcoded model versions), **Vendor-Agnostic** examples, and architectural accuracy.
7. **`project-standardizer`**:
   - Enforces repository layout, clean folder structures, and avoidance of stray/junk files.

---

## 🎯 2. Mandatory Pre-Review Static Scan Checklist

Before writing any Review Report or assigning quality scores, the AI Agent **MUST execute static grep searches** across the target codebase to detect anti-patterns with **Zero Tolerance**:

| Check Target | Search Pattern | Related Skill | Strict Rule & Violation Penalty |
| :--- | :--- | :--- | :--- |
| **Legacy ORM 1.x Syntax** | `session.query(` in codebase | `database-architect` / `python-enterprise-stack` | **🚨 CRITICAL**: Deprecated 1.x syntax. MUST use Pure SQLAlchemy 2.0 (`select()`, `update()`, `delete()`, `session.scalars()`). |
| **Raw SQL & Cursor Usage** | `cursor.execute`, `sqlite3.connect`, `get_db_connection` | `database-architect` | **🚨 CRITICAL (Auto-FAIL DB Layer)**: Absolutely NO raw SQL or cursor manipulation allowed in application/master logic. Every DB interaction MUST use SQLAlchemy ORM (`get_db_session()`, Entity Models). |
| **Silent Fallback Configs** | `settings.get("...", default)` for schema-defined keys | `python-enterprise-stack` | **⚠️ WARNING**: Must fail fast and loud at boot time via Pydantic validation rather than hiding configuration errors with silent code fallbacks. |
| **Bare Print Statements** | `print(` in source files | `python-enterprise-stack` | **⚠️ WARNING**: Must use structured `loguru.logger` instead of stdout prints. |
| **Hardcoded Secrets** | `AIzaSy`, `sk-`, `password =`, `api_key = "..."` | `security-auditor` | **🚨 CRITICAL**: All secrets must be loaded dynamically via `.env` / `os.getenv()`. |
| **Non-English Code Artifacts** | Thai/Regional non-ASCII in comments or docstrings | `documentation-generator` | **⚠️ WARNING**: Comments, docstrings, and debug logs must be in **English only**. |
| **Hardcoded Models & Brand Names** | Specific model versions or vendor brand names in docstrings | `documentation-generator` | **⚠️ WARNING**: Docstrings and comments must be model-agnostic and vendor-agnostic. |

---

## 📐 3. Review Audit Dimensions

The AI Agent MUST evaluate the target code across the following dimensions without leniency:

1. **💾 Database & ORM Compliance (`database-architect`)**:
   - **Zero Tolerance Policy**: Reject any raw SQL, manual cursor queries, or legacy `session.query()` calls.
   - Confirm all DB operations use Pure SQLAlchemy 2.0 syntax with transactional context managers or FastAPI `Depends()`.
2. **🛡️ Security & Secret Safety (`security-auditor`)**:
   - Check for hardcoded API keys, secrets, passwords, or tokens.
   - Verify input sanitization and prevention of injection vulnerabilities.
3. **🐛 Logic Correctness & Edge Cases**:
   - Check for null pointers, undefined variable references, off-by-one errors, and boundary conditions.
   - Verify that exception handling is explicit and does NOT swallow errors silently (`except: pass`).
4. **⚡ Performance & Resilience (`refactoring-expert`)**:
   - Identify redundant DB queries, N+1 query patterns, missing rate-limit retries (exponential backoff), or missing fast-path bypasses.
5. **🧪 Testability & Clean Architecture (`test-suite-generator`)**:
   - Verify decoupling between UI, API, and Core Engine.
   - Confirm test suite passes 100% with explicit resource teardown on Windows (`engine.dispose()`, `gc.collect()`).
6. **📝 Logging & Observability Audit (`python-enterprise-stack`)**:
   - Verify structured logger usage (`loguru`) instead of bare `print()`.
7. **🏷️ Enum & Constants Compliance**:
   - Confirm domain statuses, priority levels, and system paths use centralized constants or strongly-typed `Enum` classes instead of inline hardcoded string literals.

---

## 🤖 4. Execution Workflow

1. **Perform Automated Static Scan**:
   - Run grep searches for forbidden patterns (`session.query(`, `cursor.execute`, `print(`, hardcoded keys).
2. **Perform Multi-Dimensional Audit**:
   - Evaluate code against all audit dimensions across the skills above.
3. **Zero-Leniency Grading**:
   - If any violation exists, the dimension **MUST be marked as FAILED / REQUIRES REFACTOR**.
4. **Generate Code Review Report**:
   - Present findings organized by severity:
     - 🚨 **Critical**: Raw SQL, legacy `session.query()`, security risks, unhandled crashes.
     - ⚠️ **Warning**: Silent fallback defaults, code smells, missing logs, bare print statements.
     - 💡 **Suggestion**: Strategy pattern refactoring, centralized constants, clean code tips.
5. **Provide Actionable Refactor Diffs**:
   - Include code diff snippets showing exact recommended fixes.
