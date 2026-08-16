# Project Rules & Coding Standards

This document defines the rules and conventions that AI agents and developers must follow when writing code in this repository.

## Coding Conventions

### 1. Code Comments & Documentation
- **All code comments, docstrings, and technical documentation inside code files MUST be written in English.**
- Do not write Thai characters in code comments, docstrings, or debug log statements.
- Technical explanations of functions, classes, and logic must be clear and concise.

### 2. Naming Conventions
- Variable names, function names, class names, and file names must be in English.
- Use `snake_case` for python variables and functions.
- Use `PascalCase` for python classes.

### 3. User Interface (UI) Strings
- **User-facing labels, buttons, forms, and instructions in the Streamlit UI SHOULD be in Thai** (as requested by the user for the web interface experience).
- Error messages displayed to users can be in Thai or English with clear instructions.

## Agent Constraints

### 4. Agent Behaviors & Approvals
- **Do NOT modify any code files (.py, .json, .txt, .bat, etc.) without explicit user approval of the implementation plan.**
- Before executing any modifying actions on the source code, the agent must present the implementation plan and wait for the user to review and explicitly approve it.
