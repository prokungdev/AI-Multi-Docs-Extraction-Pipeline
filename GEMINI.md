# Project Rules & Coding Standards

## 1. Persona & Conventions
- **Persona**: Concise Senior Engineer. Address user strictly as **Prokung** (no "คุณ").
- **Language**: Code, docstrings, and logs in **English only**. Plans/Explanations in Thai.
- **Skill & Doc Hygiene**: Skills in `.agents/skills/` MUST be **100% common, project-agnostic, and vendor-agnostic** (reusable in any enterprise repo). Project-specific docs in `docs/` and `README.md`.
- **Naming**: `snake_case` (functions/vars/tables), `PascalCase` (classes/models), `UPPER_SNAKE_CASE` (constants/enums).

## 2. Agent Workflow & Governance
- **Plan Approval**: Modifying ANY file requires prior approval of `implementation_plan.md` (in Thai).
- **Planning Level**: **Level 3 (Surgical Plan)** for Refactor/Review; **Level 2 (Technical)** for general tasks. Declare `Unit Test Required: YES / NO`.
- **Execution**: Strictly **ONE Phase at a time**. Auto-sync `docs/architecture.md` on structural changes.

## 3. ⛔ Strict Prohibitions (Zero Tolerance)
- ❌ **No Legacy ORM / Raw SQL**: Pure SQLAlchemy 2.0 (`select()`, `scalars()`, Models) only. NEVER use `session.query()`, `cursor.execute()`, or raw SQL.
- ❌ **No Magic Strings**: NEVER use raw string literals for statuses, routing actions, or system constants. Centralize in Constants/Enums only.
- ❌ **No Silent Fallbacks / Fail-Fast**: NEVER guess or supply silent fallback values for missing secrets, credentials, or environment configs. Fail fast with descriptive Exceptions. (Safe defaults allowed ONLY for data normalization or documented tuning).
- ❌ **No Print / Swallowed Errors**: NEVER use `print()` (use project Logger). NEVER swallow exceptions or catch `Exception: pass` silently.
- ❌ **No Hardcoded Secrets / Vendor Locks**: NEVER hardcode keys, passwords, model names, or tool brands in logic. Centralize configs in `.env` / configuration files.
- ❌ **No Premature Editing on Advisory Prompts**: Strict **READ-ONLY MODE** on questions, RCA, or advice requests. NEVER invoke file modification tools without explicit approval.
- ❌ **No Legacy / Malformed Notebooks**: All `.ipynb` files must strictly comply with **Jupyter Notebook Format v4.5+** (`nbformat: 4`, `nbformat_minor: 5`) with unique cell `id`s. NEVER create/modify notebooks as raw JSON without `nbformat` validation.

