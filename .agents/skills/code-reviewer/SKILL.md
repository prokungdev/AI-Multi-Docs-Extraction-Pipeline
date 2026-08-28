---
name: code-reviewer
description: Audits code quality, architecture, performance bottlenecks, and security vulnerabilities across the skill ecosystem.
---

# 🔍 Code Reviewer Skill

Guides automated, comprehensive peer reviews on source code files, modules, or git diffs against enterprise software quality standards.

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
| **Silent Fallback Configs & Secret Defaults** | `.get("api_key_env", default)`, `return {}` on config load failure | `python-enterprise-stack` | **🚨 CRITICAL**: Must fail fast and loud via explicit Exceptions rather than guessing missing environment variables, credentials, or hiding load failures. |
| **Bare Print Statements** | `print(` in source files | `python-enterprise-stack` | **⚠️ WARNING**: Must use project's internal **Logger Wrapper** instead of stdout prints. |
| **Hardcoded Secrets** | `AIzaSy`, `sk-`, `password =`, `api_key = "..."` | `security-auditor` | **🚨 CRITICAL**: All secrets must be loaded dynamically via `.env` / `os.getenv()`. |
| **Non-English Code Artifacts** | Thai/Regional non-ASCII in comments or docstrings | `documentation-generator` | **⚠️ WARNING**: Comments, docstrings, and debug logs must be in **English only**. |
| **Hardcoded State & Status Literals** | `status == "..."`, `status_code in ["..."`, `action = "..."`, `state == "..."` | `python-enterprise-stack` | **🚨 CRITICAL (Auto-FAIL Code Review)**: Absolutely NO raw string literals permitted for state transitions, entity lifecycle statuses, routing actions, or system fallback placeholders. All states must reference strongly-typed `Enum` or centralized constants classes. |
| **Ghost Code & Dead Fallback Lookups** | Obsolete fallback lookups to deleted folders or legacy configuration layouts | `refactoring-expert` | **⚠️ WARNING**: Code must never retain dead fallback lookups to deprecated directory layouts or obsolete config structures. |
| **Duplicated Execution & Redundant Logic** | Redundant processing steps, double entity registrations, or copy-pasted blocks | `refactoring-expert` | **⚠️ WARNING**: Functions must be strictly idempotent and free of duplicated execution blocks or redundant file/database operations. |
| **Vocabulary Drift & Redundant Aliases** | Deprecated terms, renamed schema keys, lingering backward-compatibility function/property aliases | `python-enterprise-stack` / `refactoring-expert` | **⚠️ WARNING**: Terminology and parameters must remain 100% consistent across code, schemas, docstrings, and logging. Eliminate backward-compatibility wrapper aliases. |
| **Skill Agnostic & Tool Coupling Drift** | Repository-specific symbols, local table/function names, or third-party brand locks in `.agents/skills/` | `code-reviewer` / `project-standardizer` | **🚨 CRITICAL**: All skills in `.agents/skills/` (including `code-reviewer` itself and all sibling skills) MUST be 100% common, project-agnostic, and vendor/tool-agnostic. |
| **Missing Test Database Isolation** | Tests performing DB CRUD without isolated temp DB / env override | `test-suite-generator` / `database-architect` | **🚨 CRITICAL (Auto-FAIL Test Suite)**: Any test suite connecting directly to dev/prod database instances without temp DB isolation must be immediately rejected. |
| **Direct Project Storage Pollution in Tests** | Tests creating files or folders directly inside project's real storage tree | `test-suite-generator` / `project-standardizer` | **🚨 CRITICAL (Auto-FAIL Test Suite)**: Tests MUST generate mock files inside OS temporary directories (`tempfile.mkdtemp()`) and clean them up completely in teardown. |
| **Static Storage Path Caching** | Path/Storage managers caching `os.environ` into static attributes without dynamic resolution | `python-enterprise-stack` / `test-suite-generator` | **🚨 CRITICAL**: Storage path root properties (`.root`) must resolve environment overrides (`STORAGE_ROOT_OVERRIDE`) dynamically on every access to prevent test leakage into production storage. |
| **Monolithic Test Dumping Grounds** | Test files packing unrelated helpers, schemas, and I/O handlers together | `test-suite-generator` | **⚠️ WARNING**: Enforce Single Responsibility (1 Topic = 1 File). Unit tests and integration tests must be distinctly categorized. |
| **DDD Inward Dependency Violation** | `domain/` importing from `infrastructure/` or `apps/` | `python-enterprise-stack` / `code-reviewer` | **🚨 CRITICAL (Auto-FAIL Architecture)**: The Domain Layer (`domain/`) must remain pure and NEVER import technical adapters, database sessions, third-party SDKs, or delivery apps. |
| **Dual Source of Truth / Middleman Path Functions** | Redundant path resolution functions outside dedicated Storage Manager | `python-enterprise-stack` / `refactoring-expert` | **🚨 CRITICAL**: Filesystem path calculations must be centralized in the designated Storage Manager. Utility modules must never duplicate path resolution or act as intermediate wrappers. |
| **Indirection Chaining & Variable Relaying** | Configs referencing variables that point to other variables | `python-enterprise-stack` | **🚨 CRITICAL**: Configuration values must map directly in a single hop without multi-tier variable/secret indirection or middleman translation layers. |
| **Shallow Test Storage Watchdogs** | Test guards using `os.listdir` instead of deep recursive tree snapshots | `test-suite-generator` | **🚨 CRITICAL (Auto-FAIL Test Suite)**: Anti-pollution storage guards must take deep recursive file tree snapshots (`rglob` / `glob(**/*)`) to detect stray files in all nested subdirectories. |

---

## 📐 3. Review Audit Dimensions

The AI Agent MUST evaluate the target code across the following dimensions without leniency:

1. **💾 Database & ORM Compliance (`database-architect`)**:
   - **Zero Tolerance Policy**: Reject any raw SQL, manual cursor queries, or legacy `session.query()` calls.
   - Confirm all DB operations use Pure SQLAlchemy 2.0 syntax with transactional context managers or FastAPI `Depends()`.
2. **🛡️ Security & Secret Safety (`security-auditor`)**:
   - Check for hardcoded API keys, secrets, passwords, or tokens.
   - Verify input sanitization, path traversal prevention, and multi-tenant isolation scoping (`tenant_id`/`org_id`).
3. **🐛 Logic Correctness, Edge Cases & Zero Redundancy**:
   - Check for null pointers, undefined variable references, off-by-one errors, and boundary conditions.
   - Verify that exception handling is explicit and does NOT swallow errors silently (`except: pass`).
   - Audit for duplicate execution blocks, redundant file I/O operations, or accidental double database writes.
4. **⚡ Performance & Resilience (`refactoring-expert`)**:
   - Identify redundant DB queries, N+1 query patterns, missing rate-limit retries (exponential backoff), or missing fast-path bypasses.
   - Eliminate dead code branches and ghost fallback lookups to obsolete system paths.
5. **🧪 Testability & Clean Architecture (`test-suite-generator` / `refactoring-expert` / `python-enterprise-stack`)**:
   - **Canonical 4-Layer DDD Dependency Rule**: Verify inward dependency flow (`apps` ➔ `application` ➔ `domain` ➔ `infrastructure`). The Domain Layer (`domain/`) must remain 100% pure and decoupled from external frameworks/SDKs.
   - **Strict Model Separation**: SQLAlchemy ORM models reside strictly in `infrastructure/persistence/models.py`, while Pydantic DTOs reside in `application/dtos/`.
   - **Enforce Dual Test Isolation & Cleanup**: Confirm that all test suites execute against temporary/mock databases and temporary directories (`tempfile.mkdtemp()`) with zero artifact writes to real project storage, and verify that teardown contains explicit existence assertions (`assert not os.path.exists(...)`).
   - **1 Topic = 1 File Architecture**: Verify that tests are cleanly organized by domain/concern (Unit vs Integration) and avoid monolithic mega-test files.
   - Confirm test suite passes 100% with explicit resource teardown on Windows (`engine.dispose()`, `gc.collect()`, `shutil.rmtree()`).
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
