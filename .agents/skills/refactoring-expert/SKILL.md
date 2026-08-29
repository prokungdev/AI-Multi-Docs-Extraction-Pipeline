---
name: refactoring-expert
description: >-
  Refactors complex, legacy, or repetitive code into clean enterprise design patterns (Strategy, Registry, Adapter),
  improves maintainability, resilience, and performance while preserving 100% of existing behavior and test coverage.
---

# 🧹 Refactoring Expert Skill

This skill guides the AI Agent to clean up complex code structures, enforce the DRY (Don't Repeat Yourself) principle, eliminate magic literals, apply enterprise design patterns (Strategy, Registry, Adapter), and ensure zero regression.

---

## 🎯 1. Refactoring Goals & Principles

1. **Behavior Preservation**:
   - Refactoring MUST NOT alter external functional behavior or break existing tests.
2. **Code Simplicity & Single Responsibility (SRP)**:
   - Extract bloated monolithic functions into focused, single-purpose components.
   - Eliminate deeply nested `if/elif/else` branches and magic string literals.
3. **DRY Principle (Don't Repeat Yourself)**:
   - Consolidate duplicate data transformations, path resolutions, and connection logic into shared abstractions.
4. **Performance & Resource Hygiene**:
   - Use vectorized/generator pipelines, proper connection pooling, and explicit cleanup of OS/database handles.

---

## 🏛️ 2. Key Enterprise Refactoring Patterns

### 2.1 Strategy Pattern & Dynamic Registry
When a module performs different export, validation, or processing algorithms based on document types, file formats, or business rules:
- ❌ **Avoid**: Cascading `if format == "csv": ... elif format == "json": ...` inside core business flows.
- ✅ **Adopt Strategy Pattern**:
  1. Define an Abstract Base Class (ABC) declaring the standard contract (e.g. `BaseExporter`, `BaseProcessor`).
  2. Implement concrete strategy classes for each format or business rule.
  3. Maintain a centralized, dynamic `Registry` mapping identifiers to strategy instances.
  4. Core business logic simply calls `get_strategy(id).execute(data)`.

### 2.2 Resilient Service Wrapper (AI / Cloud API Clients)
When interacting with external APIs, Generative AI models, or remote services:
- ❌ **Avoid**: Calling third-party SDK clients directly in multiple business stages without error resilience.
- ✅ **Adopt Unified Service Layer**:
  1. Centralize the client inside a dedicated `Service` class.
  2. Wrap API calls with **Exponential Backoff Auto-Retry** for transient errors (HTTP 429 Rate Limits, 503 Service Unavailable, network timeouts).
  3. Attach real-time telemetry, token usage counting, and cost calculation hooks transparently.

### 2.3 Namespaced Constants & Zero Static Aliases Modernization
When global default variables or repeated parameter fallbacks (`param or default_fn()`) proliferate:
- ❌ **Avoid**: Floating unorganized uppercase variables, lingering flat static aliases shadowing namespaced classes, and duplicate ternary fallback checks across multiple caller files.
- ✅ **Adopt Namespaced Classes & Clean Consumption**:
  1. Group related static paths into namespace classes (e.g. `DefaultPath`), identifiers into `DefaultIdentifier`, and app metadata into `AppMetadata`.
  2. Modernize all consumer import call-sites to access constants directly via their namespaced classes (`DefaultPath.SETTINGS`).
  3. Purge all legacy flat static aliases to eliminate architectural ambiguity and maintain a single Source of Truth.
  4. Implement single-responsibility parameter resolver functions (`resolve_parameter(param)`) to enforce uniform fallback resolution everywhere.

### 2.4 Sub-routine Extraction for Entity Ingestion Pipelines
When loops or conditional branches create entities (e.g. multi-page file splits vs single files):
- ❌ **Avoid**: Duplicating entity ID generation, database creation calls, and result list appending in both branches.
- ✅ **Adopt Sub-routine Extraction**:
  1. Extract the shared entity registration into a private helper function (`_register_entity(...)`).
  2. Keep only the format-specific parsing logic in the respective branch.

---

## 🤖 3. Execution Workflow

1. **Inspect Target Module & Test Suite**:
   - Read source code, identify dependencies, and verify existing test coverage.
2. **Identify Refactoring Targets**:
   - Flag long methods, code duplication, missing abstractions, or legacy 1.x ORM patterns.
3. **Present Implementation Plan (with Mandatory Time Estimation)**:
   - Outline planned refactoring steps, showing before/after architecture and decoupled design.
   - **Mandatory Time Estimation**: Every plan MUST include a detailed time breakdown:
     - Per-phase duration estimate.
     - Total implementation duration.
     - Post-implementation verification & debrief duration.
     - Grand total end-to-end estimated time.
4. **Execute Refactor Incrementally**:
   - Apply edits cleanly while keeping public method contracts and interfaces intact.
5. **Verify Zero Regressions**:
   - Run the automated test suite to confirm 100% test pass rate after each refactoring step.
