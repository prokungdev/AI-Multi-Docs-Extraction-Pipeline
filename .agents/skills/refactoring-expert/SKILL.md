---
name: refactoring-expert
description: >-
  Refactors complex, legacy, or repetitive code to improve readability, maintainability, and performance
  while preserving 100% of existing behavior and test coverage.
---

# 🧹 Refactoring Expert Skill

This skill guides the AI Agent to clean up complex code structures, enforce the DRY (Don't Repeat Yourself) principle, optimize performance, and improve code readability.

---

## 🎯 1. Refactoring Goals

1. **Behavior Preservation**:
   - Refactoring MUST NOT alter external functional behavior or break existing tests.
2. **Code Simplicity & Readability**:
   - Extract long functions into smaller, single-purpose helper functions.
   - Remove dead code, redundant conditional branches, and magic numbers/strings.
3. **DRY Principle (Don't Repeat Yourself)**:
   - Consolidate duplicate code blocks into reusable utility functions or base classes.
4. **Performance Tuning**:
   - Replace slow loops with vectorization, list comprehensions, or efficient data structures (e.g. `set`/`dict` lookups).

---

## 🤖 2. Execution Workflow

1. **Inspect Target Module**:
   - Read source code and existing test suite.
2. **Identify Refactoring Targets**:
   - Highlight long methods, code duplication, deeply nested conditionals, or inefficient loops.
3. **Present Implementation Plan**:
   - Outline planned refactoring steps and show before/after code structure.
4. **Execute Refactor Incrementally**:
   - Apply edits cleanly while keeping method contracts intact.
5. **Verify Zero Regressions**:
   - Run automated test suite to confirm all tests pass cleanly after refactoring.
