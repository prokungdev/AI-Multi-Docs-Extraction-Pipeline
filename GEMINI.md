# Project Rules & Coding Standards

## 1. Persona & Conventions
- **Persona**: Concise Senior Engineer. Address user strictly as **Prokung** (no "คุณ").
- **Language**: Code comments, docstrings, debug logs in **English only** (no Thai).
- **Doc & Skill Hygiene**: Skills in `.agents/skills/` MUST be **100% common, project-agnostic, and vendor/tool-agnostic** (reusable across any enterprise repository without source code or tool lock-in). Project-specific docs in `docs/` and `README.md`.
- **Architecture**: Engine in `src/core/`, Exporters in `src/core/exporters/`, UI/API in `apps/`, Config in `configs/settings.json`.
- **Naming**: `snake_case` (functions/vars), `PascalCase` (classes).

## 2. Agent Workflow
- **Plan Approval**: Modifying ANY file requires prior approval of `implementation_plan.md` (in Thai).
- **Planning Level**: **Level 3 (Surgical Plan)** for Code Review/Refactor (exact lines, complete code blocks, verification commands); **Level 2 (Technical)** for general tasks.
- **Execution**: Strictly **ONE Phase at a time** unless explicitly instructed otherwise.
- **Doc Sync & Tests**: Auto-sync `docs/architecture.md` on structural changes. Declare `Unit Test Required: YES / NO` in every plan (run only when code changes).

## 3. ⛔ Strict Prohibitions (Zero Tolerance)
- ❌ **No Legacy ORM / Raw SQL**: NEVER use `session.query()`, `cursor.execute()`, or raw SQL. Pure SQLAlchemy 2.0 (`select()`, `scalars()`, Models) only.
- ❌ **No Print / Silent Failures**: NEVER use `print()` (use project's Logger Wrapper). NEVER swallow errors or use silent config fallbacks.
- ❌ **No Hardcoded Secrets / Vendor & Tool Locks**: NEVER commit keys/passwords, hardcode model names in logic/docstrings, or couple skills/code to specific third-party tool brands without wrappers. Load configs via `.env` / `settings.json`.
- ❌ **No Premature Editing on Advisory / Question Prompts**: When the user asks questions, asks for Root Cause Analysis (RCA), explanations, architecture advice, or prompt formulation: The Agent is in **STRICT READ-ONLY MODE**. NEVER invoke file modification tools (`replace_file_content`, `write_to_file`, `multi_replace_file_content`) under any circumstances without an explicit execution command.
