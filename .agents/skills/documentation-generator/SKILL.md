---
name: documentation-generator
description: >-
  Automatically scans codebase modules, database models, and system architecture to generate or update
  comprehensive, standardized technical documentation in docs/ (architecture.md, database_schema.md, installation_guide.md, README.md).
---

# 📝 Technical Documentation Generator Skill

This skill guides the AI Agent to inspect codebase modules, database schemas, and configuration parameters to generate or maintain enterprise-grade software documentation.

---

## 🎯 1. Target Documentation Suite

When executed, this skill manages four core documentation artifacts inside the repository:

### A. System Architecture (`docs/architecture.md`)
Must contain:
- **System Overview**: Business goals, high-level capabilities, system boundaries, and target user domains.
- **Component Diagram**: A clear `mermaid` flowchart rendering interactions between system entry points, core processing stages, database storage, and external integrations.
- **Processing Stage Breakdown**: Detailed descriptions of each core processing stage or service layer.
- **Module Responsibilities**: Summary of services, modules, and components across the codebase.

### B. Database Schema & Data Models (`docs/database_schema.md`)
Must contain:
- **ER Diagram**: A `mermaid` entity relationship diagram depicting primary keys, foreign key constraints, and entity relationships.
- **Table Specifications**: Detailed Markdown tables enumerating column names, data types, constraints (NOT NULL, UNIQUE), and business meanings for all database models.
- **Indexing & Queries**: Key indices and sample database queries used in the application.

### C. Installation & Environment Guide (`docs/installation_guide.md`)
Must contain:
- **Prerequisites**: Required OS, runtime version (Python/Node/Go/Java), Git, and environment variables.
- **Automated Setup**: Instructions for running automated setup scripts or commands (configuring environment, dependencies, `.env`, git hooks, and DB schemas).
- **Manual Setup Steps**: Commands for manual environment activation, dependency installation, and environment configuration.
- **Troubleshooting**: Diagnostic steps for common setup errors and runtime configuration issues.

### D. Root Landing Page (`README.md`)
Must contain:
- Project summary, high-level capabilities, and architecture diagram.
- Quick start instructions linking to `docs/installation_guide.md`.
- Relative Markdown links pointing to all documentation files in `docs/`.

---

## 📏 2. Documentation Guidelines & Hygiene

1. **Relative Links Only**: ALL markdown file links MUST use clean relative links (e.g. `docs/installation_guide.md`). NEVER use local absolute `file:///` URLs.
2. **Valid Mermaid Diagrams**: Quote labels containing special characters and ensure diagram syntax compiles cleanly.
3. **Synchronization with Codebase**: Always verify code imports, function signatures, and database table definitions against active source files before writing documentation.

---

## 🤖 3. AI Execution Steps

When triggered to **generate** or **update** project documentation, follow these steps:

1. **Inspect Codebase**:
   - Inspect source modules for application architecture.
   - Inspect database models for schema definitions.
   - Inspect system configuration files.
2. **Audit Existing Docs**:
   - Check if `docs/architecture.md`, `docs/database_schema.md`, `docs/installation_guide.md`, and `README.md` exist and are up to date.
3. **Present Implementation Plan**:
   - List missing or outdated documentation files and present an `implementation_plan.md` artifact to the user.
4. **Generate & Update Docs**:
   - Write/Update target markdown documentation files using `write_to_file`.
   - Verify that all internal links are relative and all mermaid diagrams render cleanly.
