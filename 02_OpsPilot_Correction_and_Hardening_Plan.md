# OpsPilot AI — Correction & Hardening Plan

## Purpose

OpsPilot is the strongest current **enterprise agentic AI workload** in the portfolio.

Position it as:

> **A deterministic enterprise document-agent platform combining document intelligence, RAG, agent orchestration, business-rule validation, human approval, and auditable workflows.**

The invoice/PO automation flow is the reference workload; the underlying architecture should remain reusable.

---

# 1. Strengths Already Present

The inspected repository already contains:

- FastAPI
- React
- LangGraph-oriented workflow architecture
- async ingestion
- structured extraction
- deterministic validation
- 3-way PO reconciliation
- RAG policy retrieval
- citations
- human-in-the-loop review
- RBAC
- multi-tenancy
- audit trail
- Redis
- PostgreSQL/SQLite support
- Docker Compose
- benchmark suite
- LLM provider abstraction
- Prometheus-style metrics

Keep the principle:

> **The database is authoritative; the LLM only proposes.**

---

# 2. Critical Credibility Fix — Latency

The repository currently reports approximately **0.86–0.89 ms** as mean end-to-end processing latency.

That should not be presented as real LLM-backed document processing latency unless the measured path truly includes the document parsing, retrieval, model calls, and final workflow.

### Required change

Rename/qualify it, for example:

> Deterministic benchmark execution latency

and separately measure:

| Metric | Measurement |
|---|---|
| deterministic pipeline latency | actual |
| real LLM end-to-end latency | actual |
| RAG retrieval latency | actual |
| LLM generation latency | actual |

Never use mock latency as evidence of production AI latency.

---

# 3. Separate Mock and Real Evaluation

The current benchmark uses a `MockLLMProvider`.

That's valid for deterministic regression tests, but it must not be conflated with real model-quality evaluation.

## Mode A — Deterministic regression

Test:

- classification rules
- extraction schema
- PO reconciliation
- business policy
- routing
- prompt-injection containment
- workflow state transitions

## Mode B — Real LLM evaluation

Test:

- extraction quality
- classification quality
- RAG grounding
- citation correctness
- agent task success
- safety

Report separately:

```text
Regression: 50/50 passed
Real LLM: 47/50 passed
Faithfulness: measured
Answer correctness: measured
Latency: measured
Cost: measured or explicitly estimated
```

Only publish actual results.

---

# 4. Evaluation Methodology

Add:

```text
evals/METHODOLOGY.md
```

Document:

- dataset creation/source
- labels
- categories
- evaluator logic
- formulas
- model/provider
- prompt version
- embedding model
- environment
- random seed where relevant
- known limitations

Do not use invented phrases such as “Industry Standard Enterprise GenAI Reliability Standard” unless an external standard is actually being followed and cited.

Prefer:

> Project Evaluation Specification

---

# 5. Hardcoded Demo Credentials

The inspected seed code contains obvious development passwords such as:

```text
admin123
ops123
reviewer123
viewer123
```

Replace them with environment-backed values:

```text
DEMO_ADMIN_PASSWORD
DEMO_OPS_PASSWORD
DEMO_REVIEWER_PASSWORD
DEMO_VIEWER_PASSWORD
```

Document clearly that demo credentials are local-development-only.

---

# 6. Multi-Tenant Isolation

Enforce tenant isolation server-side.

Target:

```text
JWT
 ↓
User
 ↓
Tenant
 ↓
Role
 ↓
Resource ownership
```

Add an explicit cross-tenant test:

```text
Tenant A user
    ↓
Tenant B resource
    ↓
Denied
```

Do not rely on frontend filtering.

---

# 7. RAG Hardening

Verify the real retrieval path:

```text
Document
 ↓
Chunk
 ↓
Embedding
 ↓
Vector store
 ↓
Retrieval
 ↓
Policy context
 ↓
Decision
```

Every result should expose:

- document id
- title
- page
- chunk
- score

Test:

- wrong-policy retrieval
- missing document
- conflicting policies
- tenant-isolated retrieval
- malicious instructions inside retrieved documents

---

# 8. Agent Safety

Keep deterministic boundaries outside the model:

```text
LLM Proposal
 ↓
Schema Validation
 ↓
Business Rules
 ↓
Authorization
 ↓
Risk Policy
 ↓
Human Approval if required
 ↓
Side Effect
```

The LLM must never directly perform irreversible financial/database actions.

---

# 9. Persistent Human-in-the-Loop State

Persist workflow states in the database.

Recommended states:

```text
QUEUED
PROCESSING
REVIEW_REQUIRED
APPROVED
REJECTED
COMPLETED
FAILED
```

The system must be restart-safe for review workflows.

---

# 10. Observability Upgrade

Add/verify:

- OpenTelemetry traces
- structured logs
- correlation/request IDs
- Prometheus metrics

Trace:

```text
upload
 ↓
classification
 ↓
extraction
 ↓
validation
 ↓
retrieval
 ↓
decision
 ↓
ERP action
```

Track:

- queue delay
- processing duration
- extraction failures
- validation failures
- RAG latency
- LLM latency
- token usage
- cost
- manual review rate
- auto-approval rate

---

# 11. Evaluation Table Cleanup

Current benchmark presentation is visually strong but must be traceable.

Use:

| Metric | Result | Dataset | Mode |
|---|---:|---:|---|
| classification accuracy | actual | N cases | deterministic/real |
| extraction exact match | actual | N cases | deterministic/real |
| citation recall | actual | N cases | RAG |
| injection defense | actual | N cases | security |
| latency | actual | N runs | runtime |
| cost/document | actual | N runs | estimated/real |

Clearly distinguish **measured**, **estimated**, and **simulated** values.

---

# 12. Docker Hardening

The current Compose configuration contains demo credentials directly.

Move secrets to environment configuration.

Add where appropriate:

- non-root containers
- pinned images where practical
- health checks
- restart policies
- dev/prod configuration separation

Do not call it production-hardened until those controls are real.

---

# 13. API Hardening

Verify:

- upload size limits
- MIME/content validation
- timeouts
- retries
- idempotency where needed
- request IDs
- pagination
- consistent error schemas
- rate limiting
- server-side authorization

Async ingestion should follow:

```text
POST /upload
 ↓
202 Accepted
 ↓
job_id
 ↓
GET job status
```

---

# 14. Storage Abstraction

Create:

```text
StorageBackend
 ├── LocalStorage
 └── S3CompatibleStorage
```

Use local storage for development.

Only claim object-storage integration once a real adapter exists and is tested.

---

# 15. CI/CD

Ensure CI runs:

```bash
uv sync --frozen
uv run pytest -v
```

Also run:

- Ruff
- mypy
- frontend build/tests
- security/dependency scanning

A failed safety/regression evaluation should be capable of blocking release.

---

# 16. Demo Scenarios

Create reproducible predefined scenarios.

## 1. Clean

```text
Invoice
 ↓
Matching PO
 ↓
Policy passes
 ↓
Auto approval
```

## 2. PO mismatch

```text
Invoice
 ↓
Variance
 ↓
Review queue
```

## 3. High value

```text
Invoice > threshold
 ↓
Mandatory approval
```

## 4. Prompt injection

```text
Malicious document text
 ↓
Deterministic policy rejects override
 ↓
Workflow remains safe
```

---

# 17. Portfolio Positioning

README title should be:

> **OpsPilot AI — Enterprise Document & Workflow Agent Platform**

Do not lead with “AI invoice demo”. Call invoice/PO automation the **reference workflow**.

---

# 18. Definition of Done

- [ ] latency metric is accurately named
- [ ] mock and real evaluations are separate
- [ ] evaluation methodology documented
- [ ] demo passwords removed from source
- [ ] cross-tenant isolation tested
- [ ] real RAG path verified
- [ ] citation provenance verified
- [ ] agent safety boundaries tested
- [ ] human-review state is persistent
- [ ] telemetry is real
- [ ] Docker configuration is cleaned up
- [ ] CI is green
- [ ] README matches implementation
- [ ] all published benchmark values are reproducible

---

# Interview Story

> “The LLM handles unstructured understanding, but the database remains the system of record. Extraction and classification can be probabilistic, while financial calculations, PO matching, access control, workflow state transitions, and irreversible writes remain deterministic. Exceptions become persistent human-review states, and the whole process is auditable.”
