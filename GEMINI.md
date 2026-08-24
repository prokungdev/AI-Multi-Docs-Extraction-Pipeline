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
- **Execution**: Strictly ONE phase at a time. Auto-sync `docs/architecture.md` on structural changes.

## 3. ⛔ Strict Prohibitions (Zero Tolerance)
- ❌ **No Legacy ORM / Raw SQL**: Pure SQLAlchemy 2.0 (`select()`, `scalars()`, Models) only. No `session.query()`, `cursor.execute()`, or raw SQL.
- ❌ **No Magic Strings**: Use centralized Constants/Enums only for statuses and routing.
- ❌ **No Silent Fallbacks (Fail-Fast)**: Never guess missing secrets or configs. Raise explicit Exceptions.
- ❌ **No Print / Swallowed Errors**: Use project Logger (no `print()`). Never catch `Exception: pass` silently.
- ❌ **No Hardcoded Secrets / Vendor Locks**: Centralize keys, models, and paths in `.env` / configs.
- ❌ **No Premature Edits on Advisory Requests**: Strict READ-ONLY mode on questions, RCA, or advice.
- ❌ **No Malformed Notebooks**: `.ipynb` must strictly comply with **Jupyter v4.5+** (`nbformat: 4.5`) with unique cell `id`s.
