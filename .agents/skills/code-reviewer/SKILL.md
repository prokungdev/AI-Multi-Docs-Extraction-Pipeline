---
name: code-reviewer
description: >-
  Audits code quality, identifies logic bugs, unhandled edge cases, performance bottlenecks, and security vulnerabilities.
  Generates a structured Code Review Report before committing or merging.
---

# 🔍 Code Reviewer Skill

This skill guides the AI Agent to perform comprehensive automated peer reviews on source code files or git diffs against software quality standards.

---

## 🎯 1. Review Audit Dimensions

When triggered, the AI Agent MUST evaluate the target code across five key dimensions:

1. **🛡️ Security & Secret Safety**:
   - Check for hardcoded API keys, secrets, passwords, or tokens.
   - Verify input sanitization and prevention of injection vulnerabilities (SQLi, Command Injection).
2. **🐛 Logic Correctness & Edge Cases**:
   - Check for null pointers, undefined variable references, off-by-one errors, and boundary conditions.
   - Verify that exception handling is explicit and does NOT swallow errors silently (`catch {}` or `except: pass`).
3. **⚡ Performance & Memory Efficiency**:
   - Identify redundant DB queries, N+1 query patterns, memory leaks, or unnecessary synchronous blocking calls.
4. **🧪 Testability & Clean Architecture**:
   - Evaluate Single Responsibility Principle (SRP) and check if function signatures are modular and easily testable.
5. **📐 Workspace Coding Standards**:
   - Ensure compliance with `.agents/rules/coding-standards.md` (English comments/docstrings, standard naming conventions).
6. **📝 Logging & Observability Audit**:
   - Verify structured logger usage (e.g. `loguru`) instead of bare `print()` / `console.log()` statements.
   - Confirm key function entrances and business milestones record `INFO`/`DEBUG` logs.
   - Confirm exception blocks explicitly log errors with stack traces (`logger.error()`).
7. **🩺 System Health & Readiness Audit (Recommended)**:
   - Check if entry points or web startup handlers validate DB, environment credentials, and storage readiness before allowing user transactions.

---

## 🤖 2. Execution Workflow

1. **Inspect Code / Staged Diff**:
   - Read the target source files using `view_file` or check staged changes via `git status` / `git diff`.
2. **Perform Multi-Dimensional Audit**:
   - Evaluate code against all 7 review dimensions above.
3. **Generate Code Review Report**:
   - Present findings organized by severity:
     - 🚨 **Critical**: Security risks, unhandled crashes, or severe data loss bugs.
     - ⚠️ **Warning**: Code smells, missing error handling, missing logs, or performance bottlenecks.
     - 💡 **Suggestion**: Formatting, naming consistency, and clean code refactoring tips.
4. **Provide Suggested Refactor Diffs**:
   - Include code diff snippets showing exact recommended fixes.
