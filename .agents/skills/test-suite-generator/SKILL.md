---
name: test-suite-generator
description: >-
  Scans codebase modules, functions, and API endpoints to generate comprehensive, decoupled unit and integration test suites
  with realistic mock data and edge case scenarios.
---

# 🧪 Test Suite Generator Skill

This skill guides the AI Agent to inspect target source code modules and construct robust, automated unit and integration tests.

---

## 🎯 1. Testing Standards & Coverage

When executed, the generated test suites MUST adhere to the following principles:

1. **Framework & Runner**:
   - Use the project's standard test runner (e.g. `pytest` for Python, `jest` / `vitest` for JS/TS, `go test` for Go).
2. **Comprehensive Coverage**:
   - **Happy Path**: Normal valid inputs and standard expected workflows.
   - **Edge Cases**: Empty inputs, null/none values, invalid data types, boundary values, and large payloads.
   - **Error Handling**: Exception handling, failure response codes, and invalid parameters.
3. **Realistic Mocking & Isolation**:
   - Mock external network calls (e.g. AI API endpoints, third-party HTTP APIs) and external databases so tests run deterministically, fast, and in isolation.
4. **Decoupled & Generic Test Data**:
   - **Domain Agnostic**: NEVER hardcode specific company names, vendor IDs, or environment-specific folder names in test code.
   - **Generic Mock Identifiers**: Use generic placeholders (e.g. `mock_source`, `sample_entity`, `test_vendor_01`) or resolve parameters dynamically from project configuration.
5. **Test Naming Convention**:
   - Use clear, descriptive test function names, e.g. `test_process_input_success()`, `test_validate_record_invalid_format_returns_false()`.

---

## 🤖 2. Execution Workflow

1. **Inspect Target Module**:
   - Inspect the target source file to understand function signatures, parameters, return types, and business rules.
2. **Analyze Test Requirements**:
   - Identify happy paths, edge cases, and external dependencies that require mocking.
3. **Propose Test Structure**:
   - Outline planned test cases and file target locations following repo conventions.
4. **Generate Test Suite**:
   - Create clean, decoupled test files using generic mock data and dynamic configuration resolution.
5. **Verify Execution**:
   - Run test runner to verify all generated tests pass cleanly with zero warnings or failures.
