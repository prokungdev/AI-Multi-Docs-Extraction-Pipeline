---
name: code-reviewer
description: >-
  Audits code quality, identifies logic bugs, unhandled edge cases, performance bottlenecks, and security vulnerabilities.
  Integrates python-enterprise-stack and security-auditor standards into structured Code Review Reports.
---

# 🔍 Code Reviewer Skill

This skill guides the AI Agent to perform comprehensive automated peer reviews on source code files or git diffs against software quality standards.

---

## 🔗 1. Referenced Skill Dependencies

When this skill is invoked, the AI Agent MUST read and incorporate standards from the following reference skills:
- **`python-enterprise-stack`**: Check SQLAlchemy 2.0 ORM patterns (`get_db_session`), Dual Logging (Loguru + SQLite), Pydantic v2 validation, type annotations, and English docstring conventions.
- **`security-auditor`**: Check secret safety, OWASP risks, SQL injection, and path sanitization.

---

## 🎯 2. Review Audit Dimensions

The AI Agent MUST evaluate the target code across seven key dimensions:

1. **🛡️ Security & Secret Safety**:
   - Check for hardcoded API keys, secrets, passwords, or tokens.
   - Verify input sanitization and prevention of injection vulnerabilities (SQLi, Command Injection).
2. **🐛 Logic Correctness & Edge Cases**:
   - Check for null pointers, undefined variable references, off-by-one errors, and boundary conditions.
   - Verify that exception handling is explicit and does NOT swallow errors silently (`catch {}` or `except: pass`).
3. **💾 Database & ORM Compliance (`python-enterprise-stack`)**:
   - Confirm DB operations use SQLAlchemy ORM models or `get_db_session()` context manager instead of raw un-parameterized SQL.
   - Verify dynamic absolute path resolution for DB files.
4. **⚡ Performance & Memory Efficiency**:
   - Identify redundant DB queries, N+1 query patterns, memory leaks, or unnecessary synchronous blocking calls.
5. **🧪 Testability & Clean Architecture**:
   - Evaluate Single Responsibility Principle (SRP) and check if function signatures are modular and easily testable.
6. **📝 Logging & Observability Audit**:
   - Verify structured logger usage (`loguru`) instead of bare `print()` / `console.log()` statements.
   - Confirm exception blocks explicitly log errors with stack traces (`logger.error()`).
7. **📐 Workspace Conventions**:
   - Confirm docstrings and comments are in **English only**.
   - Check standard naming (`snake_case` for functions/variables, `PascalCase` for classes).

---

## 🤖 3. Execution Workflow

1. **Inspect Code / Staged Diff**:
   - Read the target source files using `view_file` or check staged changes via `git diff`.
2. **Perform Multi-Dimensional Audit**:
   - Evaluate code against all 7 review dimensions above.
3. **Generate Code Review Report**:
   - Present findings organized by severity:
     - 🚨 **Critical**: Security risks, unhandled crashes, or severe data loss bugs.
     - ⚠️ **Warning**: Code smells, missing error handling, missing logs, or performance bottlenecks.
     - 💡 **Suggestion**: Formatting, naming consistency, and clean code refactoring tips.
4. **Provide Suggested Refactor Diffs**:
   - Include code diff snippets showing exact recommended fixes.
