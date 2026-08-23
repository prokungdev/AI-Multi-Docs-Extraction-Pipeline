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
   - Enforces Pydantic v2 schema validations, type hints, structured Dual Logging via internal **Logger Wrapper / Gateway**, and explicit exception handling.
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
| **Raw SQL & Cursor Usage** | `cursor.execute`, `sqlite3.connect`, `raw_connection()` | `database-architect` | **🚨 CRITICAL (Auto-FAIL DB Layer)**: Absolutely NO raw SQL or cursor manipulation allowed in application/master logic. Every DB interaction MUST use SQLAlchemy ORM (`get_db_session()`, Entity Models). |
| **Silent Fallback Configs** | `settings.get("...", default)` for schema-defined keys | `python-enterprise-stack` | **⚠️ WARNING**: Must fail fast and loud at boot time via Pydantic validation rather than hiding configuration errors with silent code fallbacks. |
| **Bare Print Statements** | `print(` in source files | `python-enterprise-stack` | **⚠️ WARNING**: Must use project's internal **Logger Wrapper** instead of stdout prints. |
| **Hardcoded Secrets** | `AIzaSy`, `sk-`, `password =`, `api_key = "..."` | `security-auditor` | **🚨 CRITICAL**: All secrets must be loaded dynamically via `.env` / `os.getenv()`. |
| **Non-English Code Artifacts** | Thai/Regional non-ASCII in comments or docstrings | `documentation-generator` | **⚠️ WARNING**: Comments, docstrings, and debug logs must be in **English only**. |
| **Hardcoded Models & Brand Names** | Specific model versions or vendor brand names in docstrings | `documentation-generator` | **⚠️ WARNING**: Docstrings and comments must be model-agnostic and vendor-agnostic. |
| **Magic Strings & Uncentralized Identifiers** | Inline hardcoded action strings, lifecycle stage folder names, status strings | `python-enterprise-stack` | **⚠️ WARNING**: State machine action states, lifecycle stage directories, and status codes MUST use centralized constants or strongly-typed Enums. |
| **Ghost Code & Dead Fallback Lookups** | Obsolete fallback lookups to deleted folders or legacy configuration layouts | `refactoring-expert` | **⚠️ WARNING**: Code must never retain dead fallback lookups to deprecated directory layouts or obsolete config structures. |
| **Duplicated Execution & Redundant Logic** | Redundant processing steps, double entity registrations, or copy-pasted blocks | `refactoring-expert` | **⚠️ WARNING**: Functions must be strictly idempotent and free of duplicated execution blocks or redundant file/database operations. |
| **Vocabulary & Schema Drift** | Lingering deprecated terms or renamed schema keys in comments, logs, or kwargs | `documentation-generator` / `project-standardizer` | **⚠️ WARNING**: Terminology and parameter names must remain 100% consistent across code, schemas, docstrings, and logging. |
| **Database Seed vs Constants Drift** | Missing states, unseeded lookups, or unpruned dead database entity models | `database-architect` | **⚠️ WARNING**: Database initialization routines and seed data must perfectly mirror application constants, and all superseded dormant tables must be pruned. |
| **Lingering Static Aliases** | Module-level flat aliases duplicating or shadowing Namespaced Constants Classes | `python-enterprise-stack` / `refactoring-expert` | **⚠️ WARNING**: All consumer modules must access constants directly via their namespaced classes; lingering flat static aliases must be eliminated. |
| **Skill Agnostic & Tool Coupling Drift** | Repository-specific symbols, local table/function names, or third-party brand locks in `.agents/skills/` | `code-reviewer` / `project-standardizer` | **🚨 CRITICAL**: All skills in `.agents/skills/` (including `code-reviewer` itself and all sibling skills) MUST be 100% common, project-agnostic, and vendor/tool-agnostic. |

---

## 📐 3. Review Audit Dimensions

The AI Agent MUST evaluate the target code across the following dimensions without leniency:

1. **💾 Database & ORM Compliance (`database-architect`)**:
   - **Zero Tolerance Policy**: Reject any raw SQL, manual cursor queries, or legacy `session.query()` calls.
   - Confirm all DB operations use Pure SQLAlchemy 2.0 syntax with transactional context managers or FastAPI `Depends()`.
2. **🛡️ Security & Secret Safety (`security-auditor`)**:
   - Check for hardcoded API keys, secrets, passwords, or tokens.
   - Verify input sanitization and prevention of injection vulnerabilities.
3. **🐛 Logic Correctness, Edge Cases & Zero Redundancy**:
   - Check for null pointers, undefined variable references, off-by-one errors, and boundary conditions.
   - Verify that exception handling is explicit and does NOT swallow errors silently (`except: pass`).
   - Audit for duplicate execution blocks, redundant file I/O operations, or accidental double database writes.
4. **⚡ Performance & Resilience (`refactoring-expert`)**:
   - Identify redundant DB queries, N+1 query patterns, missing rate-limit retries (exponential backoff), or missing fast-path bypasses.
   - Eliminate dead code branches and ghost fallback lookups to obsolete system paths.
5. **🧪 Testability & Clean Architecture (`test-suite-generator` / `refactoring-expert`)**:
   - Verify decoupling between UI, API, and Core Engine.
   - Confirm test suite passes 100% with explicit resource teardown on Windows (`engine.dispose()`, `gc.collect()`).
   - Verify that third-party processing engines (e.g. PDF parsing, image rendering, external APIs) are encapsulated in dedicated **Service Wrappers / Adapters** rather than directly imported across multiple business modules.
6. **📝 Logging & Observability Audit (`python-enterprise-stack`)**:
   - Verify structured logging via the project's internal **Logger Wrapper** instead of bare `print()` or direct third-party logger coupling.
   - Verify database audit logs and telemetry pass through structured, type-safe Data Transfer Objects (DTO).
7. **🏷️ Enum & Constants Compliance (`python-enterprise-stack`)**:
   - Confirm action states, lifecycle stage directories, status codes, priority levels, and system paths use centralized constants or strongly-typed `Enum` classes instead of inline hardcoded string literals.
   - Enforce **Zero Static Aliases**: Verify that constants are imported and accessed directly via their namespaced classes without lingering flat module-level aliases.
8. **📖 Vocabulary, Schema & Configuration Integrity (`documentation-generator` / `python-enterprise-stack`)**:
   - Ensure consistency of domain concepts, field names, and configuration keys across all layers (schemas, core engines, docstrings, and debug logs) with zero residual legacy naming drift.
   - Verify that configuration schemas implement **Cross-Field Hierarchy & Semantic Parity** checks, dynamic environment variable resolution from schemas (no hardcoded env keys), and boot-time storage write permission probes.
9. **🏛️ Database Seed & Reference Table Synchronization (`database-architect`)**:
   - Confirm reference table seed data strictly matches application state constants with zero state drift.
   - Ensure all obsolete, dormant, or superseded tables and associated CRUD helpers are completely purged.
10. **🧬 Skill Ecosystem Hygiene & Self/Cross-Skill Audit (`code-reviewer`)**:
    - **Self & Sibling Skill Audit**: Whenever skills in `.agents/skills/` are reviewed, updated, or created, the AI Agent MUST audit the modified skill itself and all referencing/sibling skills across the entire ecosystem.
    - **Zero Source Code Coupling**: Enforce that NO skill contains repository-specific source code symbols, local module paths, internal table/column names, or hardcoded project configurations.
    - **Zero Vendor & Tool Lock-in**: Enforce that NO skill contains proprietary third-party tool brands or vendor lock-in; all external capabilities must be described as decoupled wrappers, adapters, or generic provider protocols.
    - **100% Universal Enterprise Reusability**: Ensure every skill represents a standalone, universal standard drop-in reusable across any enterprise repository without modification.

---

## 🤖 4. Execution Workflow

1. **Perform Automated Static Scan**:
   - Run grep searches for forbidden patterns (`session.query(`, `cursor.execute`, `print(`, hardcoded keys).
   - When inspecting or modifying `.agents/skills/`, run self-audit and cross-skill scan to ensure zero project-specific or vendor-locked terms.
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
6. **Mandatory Level 3 Surgical Remediation Plan Standard**:
   - When generating an `implementation_plan.md` for refactoring or remediating review findings, the plan **MUST ALWAYS be at Level 3 (Surgical Plan)** for deterministic, multi-agent handoff:
     - **Exact Target Files**: Clickable markdown links with full repository paths.
     - **Exact Line Ranges**: Target line numbers for current code and replacement code.
     - **Complete Before/After Code Blocks**: Full, drop-in replacement code snippets without omitting critical logic or ambiguous ellipses (`...`).
     - **Explicit Import Management**: Exact list of all added, modified, or removed import statements.
     - **Verification Commands & Expected Outputs**: Specific CLI commands (e.g., static grep patterns, unit test runners) and their exact expected outputs.
