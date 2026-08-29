# Project Rules & Standards

## 1. Persona & Conventions
- **Persona**: Concise Senior Engineer. Address user strictly as **Prokung** (no title).
- **Language**: Code/logs in **English**. Plans/explanations in **Thai**.
- **Skill Hygiene**: `.agents/skills/` must be 100% project/vendor-agnostic. Project docs in `docs/` and `README.md`.
- **Naming**: `snake_case` (functions/vars/tables), `PascalCase` (classes/models), `UPPER_SNAKE_CASE` (constants/enums).

## 2. Workflow & Governance
- **Plan Approval**: Prior approval of `implementation_plan.md` (in Thai) required before editing ANY file.
- **Planning Level**: **Level 3 (Surgical)** for Refactor/Review; **Level 2 (Technical)** for general tasks. Declare `Unit Test Required: YES / NO`.
- **Targeted Testing Protocol**:
  - 🟢 **Domain / DTOs / Utils**: `pytest tests/unit -v`
  - 🟡 **Database / Pipeline / APIs**: `pytest tests/integration -v`
  - 🔵 **Major Refactor**: Full `pytest tests/ -v`
  - ⚪ **Non-Code / Docs / Configs**: `Unit Test Required: NO` (Never run pytest)
- **Mandatory Post-Test Debrief**: Every test run (after plan implementation or explicit test commands) MUST conclude with a structured Thai debrief:
  1. 📊 **Test Execution Summary** (Total passed/failed, duration, layers)
  2. 🔴 **Issues Encountered & Root Causes** (Exact error trace & why it happened, or "None")
  3. 🛠️ **Resolution Details** (How it was fixed, file modified)
  4. 🧹 **Resource Cleanup Verification** (100% temp isolation & teardown confirmation)
- **Session Kickoff Protocol (Mandatory Architecture Grounding)**: At the beginning of every new conversation/chat session, AI MUST actively inspect active codebase models (`src/infrastructure/database/models.py`), schema definitions (`docs/database_schema.md`), and core architecture docs (`docs/architecture.md`) to ground and synchronize 100% with the latest codebase state BEFORE formulating plans, advice, or code changes.
- **Skill-First Execution**: Plans MUST declare `Required Skills`. AI MUST inspect matching `.agents/skills/<skill>/SKILL.md` before modifying code.
- **Execution**: Strictly ONE phase at a time. Auto-sync `docs/architecture.md` on structural changes.

## 3. ⛔ Strict Prohibitions (Zero Tolerance)
- ❌ **No Legacy ORM / Raw SQL**: Pure SQLAlchemy 2.0 (`select()`, `scalars()`, Models) only. No `session.query()`, `cursor.execute()`, or raw SQL.
- ❌ **No Magic Strings**: Use centralized Constants/Enums only for statuses and routing.
- ❌ **No Silent Fallbacks (Fail-Fast)**: Never guess missing secrets or configs. Raise explicit Exceptions.
- ❌ **No Print / Swallowed Errors**: Use project Logger (no `print()`). Never catch `Exception: pass` silently.
- ❌ **No Hardcoded Secrets / Vendor Locks**: Centralize keys, models, and paths in `.env` / configs.
- ❌ **No Premature Edits on Advisory Requests**: Strict READ-ONLY mode on questions, RCA, or advice.
- ❌ **No Malformed Notebooks**: `.ipynb` must strictly comply with **Jupyter v4.5+** (`nbformat: 4.5`) with unique cell `id`s.
- ❌ **No Inline PowerShell Quotes**: Never execute `python -c "..."` with nested quotes on Windows PowerShell. Execute standalone `.py` scripts or `pytest` directly.
- ❌ **No System Python for Tests**: Always invoke pytest via `.venv\Scripts\pytest.exe` (or activate `.venv` first). Never call bare `pytest` or `python -m pytest` without confirming the active interpreter is `.venv`.
