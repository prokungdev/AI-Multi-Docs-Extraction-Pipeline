---
name: bug-fixer-debugger
description: >-
  Analyzes runtime error stack traces, test failures, and bug logs to perform root cause analysis (RCA)
  and implement minimal, surgical bug fixes without breaking existing code logic.
---

# 🐞 Bug Fixer & Debugger Skill

This skill guides the AI Agent to systematically diagnose runtime errors, test breakages, and unhandled exceptions by analyzing empirical log evidence.

---

## 🎯 1. Debugging Principles

1. **Log First, Never Guess**:
   - Inspect full, un-truncated stack traces and error logs BEFORE formulating hypotheses.
2. **Root Cause Analysis (RCA)**:
   - Trace upstream data providers and parameter invocations rather than applying superficial symptom patches (e.g. swallowing exceptions or returning dummy fallback data).
3. **Surgical Fixes**:
   - Make minimal, highly targeted modifications to fix the root cause without altering unrelated modules.
4. **Preserve API Contracts**:
   - Maintain method signatures and class schemas intact.

---

## 🤖 2. Execution Workflow

1. **Extract Empirical Logs**:
   - Read the exact error output, log file, or test failure message.
2. **Trace Failure Point**:
   - Locate the exact file and line number where the exception was raised.
   - Inspect variable states and upstream callers using `view_file`.
3. **Formulate Root Cause Explanation**:
   - Explain clearly WHY the error occurred (e.g. `ModuleNotFoundError`, `KeyError`, `AttributeError`, schema mismatch).
4. **Create Implementation Plan**:
   - Present a clear fix plan and wait for user approval before modifying code.
5. **Execute Fix & Run Verification**:
   - Apply targeted fix and re-run test/build commands to confirm success.
