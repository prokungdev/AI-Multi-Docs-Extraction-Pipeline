# 🚀 Git Workflow & Deployment Guidelines

This document defines version control, branching strategies, and CI/CD quality gate rules.

---

## 1. 📝 Conventional Commit Messages
- **Standard Prefixes**: All commit messages MUST follow conventional commit formatting:
  - `feat:` New application feature or pipeline step.
  - `fix:` Bug fix or exception handling patch.
  - `docs:` Documentation or guide updates.
  - `refactor:` Code refactoring without behavioral changes.
  - `test:` Adding or updating automated test suites.
  - `chore:` Maintenance, setup scripts, or dependency updates.

---

## 2. ⚓ Pre-Commit Quality Gates
- **Pre-Commit Hook Execution**: Version-controlled hooks (`.githooks/pre-commit`) MUST be configured and active.
- **No Secret Staging**: Never stage or commit unencrypted `.env` files or hardcoded credentials.

---

## 3. 🧪 CI/CD Quality Gates
- **100% Test Passing**: All unit and integration tests in `tests/` MUST pass cleanly before merging changes into `main`.
