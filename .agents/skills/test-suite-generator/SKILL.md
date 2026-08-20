---
name: test-suite-generator
description: >-
  Scans codebase modules, functions, and API endpoints to generate comprehensive unit and integration test suites
  with realistic mock data and edge case scenarios in tests/.
---

# 🧪 Test Suite Generator Skill

This skill guides the AI Agent to inspect source code modules in `src/` and construct robust, automated unit and integration tests under `tests/`.

---

## 🎯 1. Testing Standards & Coverage

When executed, the generated test suites MUST adhere to the following principles:

1. **Framework & Runner**:
   - Use standard test runners (e.g. `pytest` for Python, `jest` / `vitest` for JS/TS).
2. **Comprehensive Coverage**:
   - **Happy Path**: Normal valid inputs and standard workflows.
   - **Edge Cases**: Empty inputs, null/none values, invalid data types, large payloads, boundary values.
   - **Error Handling**: Exception raising, failure response codes, invalid configurations.
3. **Realistic Mocking & Isolation**:
   - Mock external API calls (e.g. Gemini AI API responses) and DB network connections so tests run deterministically and fast without external dependencies.
4. **Test Naming Convention**:
   - Use descriptive test function names, e.g. `test_split_pdf_success()`, `test_validate_tax_id_invalid_length_returns_false()`.

---

## 🤖 2. Execution Workflow

1. **Inspect Target Module**:
   - Read target source file in `src/` using `view_file` to understand function signatures, parameters, and return types.
2. **Analyze Test Requirements**:
   - Identify happy paths, edge cases, and external dependencies that require mocking.
3. **Create Implementation Plan**:
   - Propose test file location (e.g. `tests/test_<module_name>.py`) and list planned test cases.
4. **Generate Test File**:
   - Write test file using `write_to_file`.
5. **Run Verification Command**:
   - Execute test runner (e.g. `pytest`) to verify all generated tests pass cleanly.
