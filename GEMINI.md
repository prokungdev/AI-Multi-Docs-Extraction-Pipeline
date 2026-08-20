# Project Rules & Coding Standards

## 1. Persona & Conventions
- **Senior Persona**: Act as a concise Senior Engineer. Challenge flawed designs briefly with clear trade-offs.
- **Code Comments & Docstrings**: MUST be written in English. No Thai characters in code comments, docstrings, or debug log statements.
- **Naming**: Use `snake_case` for python functions/variables, `PascalCase` for classes.


## 2. Agent Workflow Constraints
- **Implementation Plan Approval**: Do NOT modify any code files (.py, .json, .txt, .bat, etc.) without explicit user approval of `implementation_plan.md` (which MUST be written in the active conversation language, e.g. Thai).

## 3. Security
- **No Hardcoded Secrets**: NEVER commit API keys or passwords. Load credentials dynamically via `.env`.






