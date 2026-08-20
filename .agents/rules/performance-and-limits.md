# ⚡ Performance & Resource Limits Guidelines

This document defines performance optimization, memory management, and resource limit rules for production stability.

---

## 1. 💾 Payload & Memory Limits
- **Max Upload File Size**: Enforce strict file size limits (e.g. Max 15MB per file) at application entry points to prevent Out-Of-Memory (OOM) crashes.
- **File Format Sanitization**: Validate file magic bytes (MIME type verification) to ensure only valid document formats (PDF, JPG, PNG, WEBP) enter the pipeline.

---

## 2. 🗄️ Database Query Efficiency
- **No N+1 Query Patterns**: Batch fetch related items or use relational JOIN queries instead of executing DB queries inside loop iterations.
- **Indexing Requirement**: Ensure indexed lookups for columns frequently used in `WHERE`, `JOIN`, and `ORDER BY` clauses (e.g., `document_id`, `created_at`, `status_code`).

---

## 3. 🧹 Resource Cleanup & Context Managers
- **Automatic Resource Disposal**: ALWAYS use context managers (`with` statements in Python) for file handles, database connections, and network sockets to guarantee resource cleanup even upon exceptions.
