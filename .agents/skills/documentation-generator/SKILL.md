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
4. **Sequential Heading & Section Integrity**: Ensure all Markdown headers and table subsection numbers (e.g., `### 2.1`, `### 2.2`) are strictly sequential, unique, and free of accidental duplicate numbers.
5. **Metric & Test Count Realism**: When documenting test suite coverage or total test counts in architecture overviews, the numbers MUST exactly match the latest live test execution results.
6. **Holistic Workspace Sweep**: When auditing documentation, verify that no temporary test files (`_temp*`, mock images, leftover journals) linger in the repository root or storage directories.

---

## 🤖 3. AI Execution Steps

When triggered to **generate** or **update** project documentation, follow these steps:

1. **Inspect Codebase & Workspace**:
   - Inspect source modules for application architecture and Clean DDD boundaries.
   - Inspect database models for schema definitions.
   - Scan workspace root and storage trees for stray temporary artifacts.
2. **Detect Stale Documents & Dead Links**:
   - Check if `docs/architecture.md`, `docs/database_schema.md`, `docs/installation_guide.md`, `README.md`, and `notebooks/README.md` contain dead links, obsolete module names, or duplicate section numbers.
3. **Present Implementation Plan**:
   - List missing or outdated documentation files and present an `implementation_plan.md` artifact to the user.
4. **Generate, Update & Sweep**:
   - Write/Update target markdown documentation files.
   - Verify that all internal links are relative, section numbers are sequential, and all mermaid diagrams render cleanly.
   - Clean up any stray temporary files discovered during the sweep.
