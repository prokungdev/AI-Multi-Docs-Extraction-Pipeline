# ⏱️ API & Network Resiliency Guidelines

This document defines the production-grade rules for network communication, external API interactions, and fault tolerance.

---

## 1. ⏱️ Mandatory Network & API Timeouts
- **Explicit Timeouts**: EVERY HTTP client request or external API invocation (e.g. Gemini AI API) MUST specify an explicit timeout value (e.g. `timeout=30s`). NEVER allow infinite or un-configured network timeouts.

---

## 2. 🔄 Exponential Backoff & Retry Policy
- **Transient Failure Handling**: Implement retry logic with exponential backoff for recoverable network errors (HTTP 503 Service Unavailable, HTTP 429 Rate Limit).
- **Maximum Retry Limit**: Cap maximum retries (e.g., max 3 retries with 2s, 4s, 8s backoff) to prevent locking system execution loops.

---

## 3. 🛡️ Graceful Degradation & Fallback Queues
- **Non-Blocking Failures**: External API failures MUST NOT crash the entire processing pipeline.
- **Review Queue Routing**: If an AI extraction or validation service fails, route the affected document into a `NEEDS_REVIEW` queue for human audit without stopping remaining batch jobs.
