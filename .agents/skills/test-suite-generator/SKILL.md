---
name: test-suite-generator
description: Generates isolated, decoupled unit and integration test suites with mock data, 1-topic-1-file structure, and cleanup verification.
---

# 🧪 Test Suite Generator Skill

Guides the generation of robust, automated unit and integration test suites adhering to enterprise architecture principles.

---

## 🎯 1. Testing Standards & Architecture

### 1.1 📦 Single Responsibility Architecture (1 Topic = 1 File)
- **Granular Test Suites**: Every test file must focus on a single domain entity, utility topic, or subsystem (e.g. `test_date_normalizer.py`, `test_pydantic_dtos.py`, `test_storage_adapter.py`).
- **NO Mega-Common Dumping Grounds**: Never dump unrelated helpers, DTOs, formatters, and I/O handlers into monolithic `test_common.py` or `test_utils.py`.

### 1.2 ⚖️ Strict Layer Separation (Unit vs Integration)
- **🟢 Unit Tests (`tests/unit/`)**:
  - **Scope**: Pure logic, algorithms, transformations, schema parsing, and parameterized validations.
  - **Dependencies**: In-memory only. Zero disk I/O, zero network, zero live database connections.
  - **Performance**: High speed (< 1s execution).
- **🟡 Integration Tests (`tests/integration/`)**:
  - **Scope**: Subsystem orchestration, ORM / database queries, storage adapters, pipelines, and HTTP endpoints.
  - **Dependencies**: Strictly isolated temporary sandboxes (`tmp_path`, `tempfile.mkdtemp()`, or in-memory SQLite).

### 1.3 🛡️ Zero-Tolerance Dual Test Isolation (Database + Storage Isolation)
- **Database Isolation (Zero DB Leakage)**: All DB tests MUST target isolated temporary databases via environment overrides. Never connect to live dev/staging/prod DBs.
- **Storage Isolation (Zero Storage Pollution)**: Never write test files into the real storage tree. Always use temporary sandbox directories.
- **Non-Production Safety Guards**: Global test fixtures must assert that DB URLs and storage roots never point to production paths (raise `RuntimeError` immediately if targeted).

### 1.4 🧹 Guaranteed Post-Test Cleanup Verification
- **Resource Teardown**: Every test fixture creating databases or files MUST execute explicit teardown (e.g. `shutil.rmtree()`, disposing DB engines, and triggering GC on Windows).
- **Explicit Verification Assertion**: Every teardown block MUST assert complete resource deletion:
  ```python
  assert not os.path.exists(temp_test_dir), f"Leakage detected: {temp_test_dir} was not cleaned up!"
  ```

### 1.5 🧩 Decoupled & Generic Test Data
- **Domain Agnostic**: Never hardcode customer names, proprietary vendor IDs, or environment-specific paths.
- **Generic Mock Identifiers**: Use generic placeholders (`sample_tenant`, `mock_entity`, `test_record_01`) or resolve parameters dynamically from fixtures.

### 1.6 🛡️ Dynamic Environment Path Resolution & Anti-Pollution Watchdogs
- **Dynamic Property Resolution**: Storage and Path managers must NEVER cache `os.environ` overrides into static instance attributes during `__init__`. Root properties (`.root`) MUST resolve `os.environ.get("STORAGE_ROOT_OVERRIDE")` dynamically on every access.
- **Deep Recursive Anti-Pollution Storage Watchdog**: Test fixtures MUST take a **deep recursive snapshot** of the real storage tree prior to execution (`glob.glob("storage/**/*", recursive=True)` or `Path("storage").rglob("*")`). Watchdogs must NEVER rely on shallow directory listings (`os.listdir`), and MUST assert that ZERO new files, mock images, temporary directories (`tmp*`), or database journals (`.db-wal`, `.db-shm`) were created in any nested level of the real storage tree. Fail the entire test suite immediately if even 1 stray file is detected.

---

## 🤖 2. Execution Workflow

1. **Inspect Target Module**: Analyze signatures, parameters, exceptions, and business rules.
2. **Classify Test Layer**: Classify as **Unit Test** (pure logic) or **Integration Test** (I/O, DB, pipeline).
3. **Propose 1-Topic-1-File Structure**: Assign dedicated test file names (e.g. `tests/unit/test_{module_topic}.py`).
4. **Generate Test Suite**: Implement decoupled tests with generic mock data, isolated temp DB/storage, and teardown assertions.
5. **Mandatory Post-Test Debrief Protocol**: Conclude every AI test execution with a 4-part structured debrief in Thai:
   1. 📊 **Test Execution Summary**: Total passed/failed, duration, layer breakdown.
   2. 🔴 **Issues Encountered & Root Causes**: Error trace and exact cause (or "None").
   3. 🛠️ **Resolution Details**: Applied fixes and modified files.
   4. 🧹 **Resource Cleanup Verification**: Explicit confirmation that zero test artifacts or databases leaked.
