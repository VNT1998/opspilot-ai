# OpsPilot AI — Complete Fix & Production Hardening Plan

## Purpose

This document is the single implementation brief for hardening `VNT1998/opspilot-ai` from a strong portfolio prototype into a credible production-oriented enterprise AI workload.

Current reviewed branch: `main`
Current reviewed head: `df584ff48ad4f68281fe54abd3d86a33455ce5b2`
Latest visible CI state: passing

## Non-Negotiable Engineering Principles

1. **The database is authoritative; the LLM only proposes.**
2. Never fabricate document contents when parsing or storage fails.
3. Every side effect must pass authorization, validation, idempotency, and audit checks.
4. Tenant isolation is always enforced server-side.
5. Mock and real AI evaluation must be separated.
6. Measured, estimated, and simulated values must never be mixed.
7. Financial values should use `Decimal`, not binary floating point, at business-rule boundaries.
8. Workflow state must survive process restarts.
9. A failed dependency must fail closed, not silently invent data.
10. README claims must reflect what is actually implemented and tested.

---

# P0 — Critical Fixes

## P0-01 — Implement real document parsing and OCR

### Problem
The API accepts PDF, DOCX, PNG, JPG, JPEG and TXT, but the worker currently attempts UTF-8 decoding and, on failure, creates synthetic invoice text. This can cause binary documents to be processed as fabricated invoices.

### Required architecture

```text
Uploaded file
    ↓
Content validation
    ↓
Document parser/router
    ├── TXT  → UTF-8 parser
    ├── PDF  → PyMuPDF text extraction
    ├── DOCX → python-docx
    ├── PNG/JPG/JPEG → OCR
    └── unsupported/corrupt → FAILED / REVIEW_REQUIRED
    ↓
Page-aware normalized text
    ↓
LangGraph workflow
```

### Implementation
Create:

```text
backend/app/services/parsing/
    __init__.py
    base.py
    router.py
    text_parser.py
    pdf_parser.py
    docx_parser.py
    image_ocr_parser.py
    result.py
```

Suggested dependencies:

```text
pymupdf
python-docx
pillow
pytesseract
```

Use `uv` for dependency management.

### Output contract

```python
class ParsedPage(BaseModel):
    page_number: int
    text: str
    confidence: float | None = None

class ParsedDocument(BaseModel):
    text: str
    pages: list[ParsedPage]
    parser: str
    parser_version: str
    extraction_warnings: list[str] = []
```

### Required behavior

- Validate file bytes, extension and MIME type.
- Do not trust only the filename extension.
- Store page-level extracted text in `DocumentPage`.
- Preserve parser name/version for reproducibility.
- Reject corrupt files explicitly.
- Do not substitute fake invoice text on parsing failures.
- Large documents must be bounded by configurable page/text limits.

### Acceptance tests

- Real PDF invoice parses correctly.
- Scanned PDF routes to OCR.
- DOCX invoice extracts expected fields.
- JPG/PNG invoice extracts OCR text.
- Invalid/corrupt binary file results in `FAILED` or `REVIEW_REQUIRED`.
- No test or code path contains fabricated fallback invoice text.

### Remove completely
Delete code patterns such as:

```python
"Binary Document Stream ..."
"Extracted Document Text ... Amount: $1450.00 ..."
```

---

## P0-02 — Lock down registration and role escalation

### Problem
`POST /api/v1/auth/register` currently accepts a caller-supplied `role`, including privileged roles.

### Required design
Public registration should either:

```text
Public registration → viewer/reviewer only
```

or be disabled in production.

Privileged roles must be assigned only through an authenticated admin flow.

### Changes
Change `UserCreate`:

```python
role: Literal["viewer", "reviewer"] = "reviewer"
```

Do not accept arbitrary roles from untrusted callers.

Prefer separate endpoint:

```text
POST /api/v1/admin/users
```

protected by:

```text
Permission.SYSTEM_CONFIG
```

### Acceptance tests

- Anonymous user cannot create an admin account.
- Anonymous user cannot create an ops_manager account.
- Reviewer cannot promote themselves.
- Viewer cannot promote themselves.
- Admin can explicitly create an allowed role.
- Cross-tenant user creation is impossible.

---

## P0-03 — Remove all hardcoded credentials and insecure production defaults

### Problem
The repository still contains demo passwords and insecure secret defaults in source, frontend code, environment examples, tests, and Docker Compose.

### Required changes

Production settings must fail startup if critical secrets are missing.

Use:

```python
SECRET_KEY: str
```

with validation requiring a strong secret in production.

For local development, generate secrets or use explicit development-only defaults.

### Demo credentials
Move them to environment variables only:

```text
DEMO_ADMIN_PASSWORD
DEMO_OPS_PASSWORD
DEMO_REVIEWER_PASSWORD
DEMO_VIEWER_PASSWORD
```

But do not publish actual password values in tracked source.

Frontend must not embed passwords.

Instead provide one of:

```text
Normal login form
```

or development-only role switch that calls a dev-only backend endpoint guarded by:

```text
ENVIRONMENT=development
```

### Docker Compose
Remove defaults such as:

```text
postgrespassword
admin123
ops123
reviewer123
viewer123
dev-insecure-secret-key...
```

Use a local `.env` that is ignored by Git.

Commit only `.env.example` with placeholders:

```text
POSTGRES_PASSWORD=change-me-locally
SECRET_KEY=generate-a-long-random-secret
```

Do not use real secrets in examples.

### Acceptance tests

- Repository search returns no actual demo password literals in application/frontend source.
- Production environment fails fast without `SECRET_KEY`.
- Frontend contains no hardcoded login passwords.

---

## P0-04 — Centralize all ERP and external side effects

### Problem
The LangGraph action node directly creates `Invoice` records, and the review API also directly writes invoices. This bypasses a single side-effect policy boundary.

### Required design
Create:

```text
backend/app/services/erp/
    service.py
    idempotency.py
```

Example service:

```python
async def post_invoice(
    *,
    tenant_id: str,
    document_id: str,
    extraction: InvoiceExtractionSchema,
    source: Literal["agent", "human"],
    actor_id: str,
) -> Invoice:
    ...
```

### Required checks

```text
Authorization
    ↓
Tenant ownership
    ↓
Document state
    ↓
Deterministic validation
    ↓
Duplicate/idempotency check
    ↓
Transaction
    ↓
Audit log
```

### Database constraints
Add strong uniqueness where appropriate, e.g. tenant + invoice number.

Use database constraints as the final duplicate defense.

### Acceptance tests

- Same approval request sent twice creates one invoice.
- Concurrent duplicate requests cannot create two invoices.
- Agent and human paths use the same ERP service.
- Unauthorized user cannot invoke the service through any API path.

---

## P0-05 — Revalidate reviewer edits before approval

### Problem
The review edit endpoint updates extracted JSON and sets `is_valid=True` without necessarily re-running all deterministic checks.

### Required flow

```text
Reviewer edits
    ↓
Pydantic schema validation
    ↓
Deterministic validation
    ↓
PO reconciliation
    ↓
Duplicate check
    ↓
Policy checks
    ↓
Risk/threshold checks
    ↓
ERP post
```

### Rules

- A reviewer cannot simply mark an invoice valid.
- Edited fields must be schema validated.
- Validation findings must be regenerated.
- The exact pre/post values must be audited.
- Final ERP posting must use the revalidated state.

### Acceptance tests

- Editing total above high-value threshold still requires the appropriate approval.
- Editing PO number to a nonexistent PO sends the item back to review.
- Editing invoice number to a duplicate blocks posting.
- Invalid Pydantic values return a validation error.
- Audit trail contains field-level changes.

---

## P0-06 — Make workflow side effects restart-safe and state-consistent

### Problem
The LangGraph execution is not persisted as a true resumable graph/checkpoint workflow. Human review is modeled in DB state, but the graph itself is recreated on every execution.

### Required design
Use persistent workflow state/checkpoints.

At minimum persist:

```text
workflow_run_id
current_step
state_version
status
retry_count
started_at
updated_at
failure_code
failure_message
```

Maintain explicit lifecycle:

```text
PENDING
RUNNING
REVIEW_REQUIRED
APPROVED
REJECTED
COMPLETED
FAILED
```

### Acceptance tests

- Kill/restart worker during processing.
- Job resumes without duplicate invoice creation.
- Review task survives restart.
- A completed workflow cannot be executed again without explicit reprocess semantics.

---

# P1 — Reliability / Architecture Fixes

## P1-01 — Replace process-local asyncio queue with durable Redis-backed queue

### Problem
`asyncio.Queue` and an in-memory list DLQ disappear when the process exits and do not work correctly across replicas.

### Required architecture

```text
FastAPI
   ↓
Redis queue
   ↓
Worker deployment(s)
   ↓
LangGraph
```

Use a queue library such as:

```text
arq
```

or another Redis-native worker library compatible with the project.

### Requirements

- durable queue
- retry count
- exponential backoff
- dead-letter queue
- job visibility/claim semantics
- idempotency key
- worker concurrency limit
- queue depth metric
- retry metric
- DLQ metric

### Acceptance tests

- Enqueue from API and process from a separate worker process.
- Redis restart behavior documented.
- Failed jobs land in DLQ after max attempts.
- Duplicate enqueue does not produce duplicate ERP effects.

---

## P1-02 — Real storage abstraction with S3-compatible backend

### Problem
Only local storage is implemented even though the architecture implies object-storage readiness.

### Required structure

```text
StorageProvider
 ├── LocalStorageProvider
 └── S3StorageProvider
```

Create:

```text
backend/app/services/storage/s3.py
```

### Requirements

- AWS S3 compatible API
- configurable endpoint for MinIO/local testing
- tenant-aware object prefixes
- content type metadata
- checksum metadata
- delete support
- signed download URLs where appropriate

### Acceptance tests

- Local storage test suite passes.
- MinIO integration test passes.
- Same document workflow works with either backend.
- Cross-tenant object access is denied.

---

## P1-03 — Real MIME/content validation

### Problem
The upload endpoint primarily validates extensions and trusts client-provided MIME.

### Required
Use magic-byte/content sniffing where practical.

Example policy:

```text
Filename extension
      +
Declared MIME
      +
Content signature
      ↓
accepted/rejected
```

Also add:

- zip bomb / decompression limits for document formats
- PDF page count limit
- image pixel dimensions limit
- text length limit
- filename normalization

---

## P1-04 — Fix financial precision

### Problem
Financial calculations use `float` throughout the ERP and validation layer.

### Required
Use `Decimal` for:

- invoice total
- subtotal
- tax
- PO total
- unit price
- variance
- currency calculations

Normalize amounts to a fixed precision before comparison.

Example:

```python
from decimal import Decimal

amount = Decimal("1450.00")
```

### Acceptance tests
Include edge cases around:

```text
0.1 + 0.2
5.00 tolerance
2.00% boundary
rounding at 0.01
```

---

## P1-05 — Fix PO tolerance rule consistency

### Problem
The methodology currently describes one interpretation of tolerance while implementation uses `OR` semantics.

### Decide and encode exactly one rule
For example:

```text
within tolerance iff
percentage_variance <= 2%
AND
absolute_variance <= $5
```

If the business policy intentionally means OR, update the methodology and tests accordingly.

### Required
Create boundary tests for:

```text
exactly 2%
exactly $5
2.01%
$5.01
```

The same rule must appear in:

- validation engine
- policy data
- methodology
- evals
- README
- tests

---

## P1-06 — Centralize authorization at the service boundary

Do not rely on route checks alone.

Every sensitive service method must verify:

```text
user identity
role/permission
tenant
resource ownership
state transition permission
```

Agent tools must inherit the caller authorization context instead of defaulting to a privileged role.

Avoid patterns where internal tool contexts default to:

```python
user_role="admin"
```

unless the service is an explicitly privileged system task with a separate capability model.

---

# P1 — RAG Hardening

## P1-07 — Upgrade RAG to real vector-store retrieval

### Current limitation
Embeddings are stored in JSON and similarities are computed in Python after loading tenant chunks.

### Required target

```text
PostgreSQL
   +
pgvector
```

Store embeddings in a real vector column.

Example conceptual model:

```text
KnowledgeChunk
 ├── tenant_id
 ├── document_id
 ├── chunk_id
 ├── page_number
 ├── content
 ├── embedding vector(N)
 └── metadata
```

### Retrieval
Use database-side similarity search and filter by tenant/ACL before returning candidates.

Target:

```text
query embedding
   ↓
pgvector similarity
   ↓
ACL filter
   ↓
optional lexical score
   ↓
hybrid reranking
   ↓
top-K
```

### Acceptance tests

- Correct semantic retrieval for paraphrased questions.
- Wrong policy is not returned merely because a token overlaps.
- Tenant isolation.
- Role ACL isolation.
- Malicious instructions inside policy documents do not become system instructions.

---

## P1-08 — Improve citation correctness evaluation

### Current limitation
A non-empty citation list can count as success.

### Required ground truth
Each RAG test case should specify:

```json
{
  "expected_document_id": "...",
  "expected_page": 1,
  "expected_policy_section": "1.1"
}
```

Evaluate:

- Recall@K
- Precision@K
- citation correctness
- source grounding
- optional MRR

A wrong document must be scored wrong even when a citation exists.

---

## P1-09 — Add retrieval quality and conflict handling

Test:

- conflicting policies
- newer vs older policy versions
- missing policy
- unauthorized policy
- ambiguous policy
- duplicate policy documents
- adversarial policy text

Implement deterministic policy precedence, e.g.:

```text
active_version
 > effective_date
 > policy_priority
 > latest_updated_at
```

Document the rule explicitly.

---

# P1 — Real AI and Evaluation Fixes

## P1-10 — Separate regression evaluation from real model evaluation

Keep two explicit modes:

```text
regression
real_llm
```

### Regression mode
Use MockLLMProvider for deterministic tests of:

- schema handling
- business rules
- state transitions
- security boundaries
- routing
- adversarial containment

### Real model mode
Use an actual provider and execute the actual model-powered path.

The live path must measure actual:

- classification
- extraction
- structured-output validity
- field accuracy
- RAG grounding
- citation correctness
- end-to-end decision accuracy
- latency
- input tokens
- output tokens
- provider cost

---

## P1-11 — Make live evaluation truly end-to-end

Current live evaluation directly exercises provider methods but does not represent full production workflow execution.

Create an evaluation mode that runs:

```text
case file
 ↓
parser
 ↓
classification
 ↓
extraction
 ↓
validation
 ↓
RAG
 ↓
decision
 ↓
action simulation
```

Do not post real invoices during evaluation. Use a safe side-effect simulator.

Example:

```text
ERP mode = dry_run
```

---

## P1-12 — Improve extraction evaluation

Current extraction scoring is too narrow.

Evaluate the entire schema:

```text
invoice_number
invoice_date
vendor_name
currency
subtotal
tax
total
payment_terms
po_number
line_items[].description
line_items[].quantity
line_items[].unit_price
line_items[].tax
line_items[].total_price
line_items[].sku
```

Report:

- exact match
- numeric tolerance match
- field-level precision/recall where appropriate
- overall document exact match

Do not call a document `100% extracted` because two fields matched.

---

## P1-13 — Use actual provider usage for token/cost telemetry

Do not hardcode:

```text
620 tokens
$0.0018
450 ms
35 ms
```

Provider responses should supply usage metadata where available.

Persist:

```text
provider
model
input_tokens
output_tokens
total_tokens
prompt_cost
completion_cost
total_cost
started_at
completed_at
duration_ms
```

For providers without cost metadata, calculate cost from a versioned pricing configuration and clearly label it as calculated.

---

## P1-14 — Measure actual component latency

Track:

```text
queue_wait_ms
parse_ms
classification_ms
extraction_ms
validation_ms
rag_embedding_ms
rag_retrieval_ms
llm_generation_ms
action_ms
total_ms
```

Remove fabricated fixed durations.

---

# P1 — Agent / LangGraph Fixes

## P1-15 — Preserve deterministic orchestration boundaries

The current LangGraph pipeline is architecturally good. Keep it.

Use the model for:

```text
classification
semantic extraction
reasoning/explanation
policy synthesis
```

Keep deterministic code for:

```text
arithmetic
PO reconciliation
thresholds
authorization
duplicate protection
ERP posting
state transitions
```

### Recommended graph

```text
INTAKE
  ↓
CLASSIFY
  ↓
EXTRACT
  ↓
VALIDATE
  ↓
RAG_POLICY
  ↓
RISK_DECISION
  ├── AUTO_APPROVE → ERP_POST
  └── REVIEW_REQUIRED → HUMAN_REVIEW
                           ↓
                       REVALIDATE
                           ↓
                         ERP_POST
```

---

## P1-16 — Make tool capabilities explicit

All agent tools should declare:

```text
name
input schema
required permission
risk level
allowed states
side effect
idempotency behavior
```

Recommended classification:

```text
READ_ONLY
REVERSIBLE
HIGH_RISK
IRREVERSIBLE
```

The graph should never directly perform a side effect that should be represented as a tool/service capability.

---

# P1 — API Hardening

## P1-17 — Add rate limiting

At minimum protect:

```text
/login
/register
/document upload
/reprocess
/knowledge search
/agent endpoints
```

Prefer Redis-backed rate limiting for multi-instance deployments.

---

## P1-18 — Add idempotency keys to mutating endpoints

Especially:

```text
POST /documents
POST /documents/{id}/reprocess
POST /reviews/{id}/approve
POST /reviews/{id}/reject
POST /reviews/{id}/edit
```

Use an idempotency record or unique constraint keyed by:

```text
tenant_id + idempotency_key + operation
```

---

## P1-19 — Improve pagination at database level

`list_documents` currently loads all tenant documents and slices them in Python.

Replace with:

```text
COUNT(*)
LIMIT
OFFSET
```

or cursor pagination for large data sets.

---

## P1-20 — Add request correlation propagation

Continue using `X-Request-ID`, but propagate it through:

```text
HTTP request
 ↓
WorkflowRun
 ↓
worker job
 ↓
LangGraph
 ↓
LLM calls
 ↓
Tool calls
 ↓
Audit logs
```

Prefer a single correlation ID plus workflow/job IDs.

---

## P1-21 — Add timeout/retry policy per dependency

Use explicit policy for:

- LLM provider
- embedding provider
- database
- Redis
- object storage
- OCR

Never retry validation/business-rule failures as though they were transient.

Classify errors:

```text
TRANSIENT
PERMANENT
VALIDATION
AUTHORIZATION
DEPENDENCY
SYSTEM
```

---

# P2 — Observability / Operations

## P2-01 — Add OpenTelemetry end-to-end

Instrument:

```text
HTTP
worker job
workflow
parser
LLM
embedding
RAG
DB
Redis
ERP service
```

Span attributes should include safe identifiers, not secrets or full sensitive document content.

---

## P2-02 — Add external trace backend support

The current implementation should be usable with an OpenTelemetry Collector.

Target:

```text
OpsPilot
   ↓
OTel Collector
   ↓
Jaeger / Tempo / compatible backend
```

Local demo can still use console/exporter mode.

---

## P2-03 — Add production metrics

Recommended metrics:

```text
opspilot_documents_uploaded_total
opspilot_documents_processed_total
opspilot_documents_failed_total
opspilot_review_required_total
opspilot_auto_approved_total
opspilot_queue_depth
opspilot_queue_wait_seconds
opspilot_processing_seconds
opspilot_llm_latency_seconds
opspilot_llm_tokens_total
opspilot_llm_cost_usd_total
opspilot_rag_latency_seconds
opspilot_rag_retrieval_score
opspilot_auth_failures_total
opspilot_cross_tenant_denials_total
opspilot_dlq_total
```

---

## P2-04 — Structured JSON logging

Log fields:

```text
timestamp
level
service
request_id
workflow_run_id
document_id
tenant_id
user_id
event
status
duration_ms
error_code
```

Never log:

- passwords
- JWTs
- API keys
- full invoice contents unless explicitly safe/redacted
- sensitive customer data unnecessarily

---

# P2 — Compliance / Audit

## P2-05 — Strengthen audit trail

For every sensitive action record:

```text
tenant
actor
actor_type
action
entity_type
entity_id
before_state
```

and:

```text
after_state
request_id
workflow_run_id
timestamp
reason
```

Consider a hash chain for tamper evidence:

```text
previous_hash + canonical_event → current_hash
```

Document that this is tamper-evident, not magically immutable if the database administrator can rewrite the database.

---

# P2 — CI/CD and Supply Chain

## P2-06 — Expand CI

CI should run:

```bash
uv sync --frozen
uv run pytest -v
uv run ruff check .
uv run mypy ...
npm ci
npm run build
```

Also add:

- dependency vulnerability scanning
- secret scanning
- container scanning
- optional SBOM generation

---

## P2-07 — Make evaluation a release gate

The deterministic regression suite must fail the build when safety/business invariants fail.

For real-model evaluation, configure a separate gated workflow because API keys/cost may not be suitable for every PR.

Define explicit thresholds instead of treating every passing script as success.

---

## P2-08 — Pin container/tool versions

Avoid:

```text
COPY --from=ghcr.io/astral-sh/uv:latest
```

Use a known tested version.

Pin base images to explicit versions and document the update policy.

---

## P2-09 — Add deployment configuration validation

For any Kubernetes/production manifests introduced later:

```text
helm lint
helm template
kubectl apply --dry-run=server
terraform fmt -check
terraform validate
terraform plan
```

Do not claim cloud production deployment until a real environment is deployed and tested.

---

# P2 — Testing Expansion

## P2-10 — Add security regression matrix

Test all roles:

```text
admin
ops_manager
reviewer
viewer
```

against:

```text
document create/read/delete/reprocess
review read/edit/approve/reject
knowledge index/search
agent run/read
audit read
metrics read
system config
```

Also test:

```text
expired JWT
wrong signing key
wrong tenant claim
inactive user
unknown role
malformed token
missing auth header
```

---

## P2-11 — Add adversarial test suite

Include:

- prompt injection in invoice text
- prompt injection in line descriptions
- prompt injection in RAG policy
- fake system messages in documents
- attempts to call high-risk tools
- role escalation payloads
- path traversal attempts
- polyglot/mismatched MIME files
- extremely large files
- duplicate uploads
- race conditions on approval

---

## P2-12 — Add workflow state-machine tests

Explicitly test all valid transitions and reject invalid ones.

Example:

```text
PENDING → RUNNING ✅
RUNNING → REVIEW_REQUIRED ✅
REVIEW_REQUIRED → COMPLETED ❌
REVIEW_REQUIRED → APPROVED ✅
APPROVED → COMPLETED ✅
COMPLETED → RUNNING ❌ unless explicit reprocess
```

---

# README / Documentation Corrections

## DOC-01 — Correct project naming

Use:

> **OpsPilot AI — Enterprise Document & Workflow Agent Platform**

Describe invoice/PO automation as the reference workflow, not the entire product.

---

## DOC-02 — Add a truthful implementation status table

Example:

| Capability | Status |
|---|---|
| FastAPI API | Implemented |
| JWT + RBAC | Implemented |
| Multi-tenancy | Implemented + tested |
| LangGraph workflow | Implemented |
| Deterministic validation | Implemented + tested |
| Mock LLM | Implemented |
| OpenAI provider | Implemented |
| Real PDF/DOCX/OCR parsing | Pending until P0-01 complete |
| Durable Redis queue | Pending until P1-01 complete |
| pgvector retrieval | Pending until P1-07 complete |
| Real end-to-end evaluation | Pending until P1-11 complete |
| External OTel backend | Optional / pending |
| Cloud deployment | Only claim after real deployment |

Do not use `Production Ready` for unverified capabilities.

---

## DOC-03 — Fix benchmark language

Every metric must be labeled:

```text
MEASURED
CALCULATED
ESTIMATED
SIMULATED
```

Do not describe a deterministic mock benchmark as proof of real-world LLM accuracy.

Do not describe a static latency sample as production latency.

---

# Recommended Final Architecture

```text
                       ┌──────────────────────┐
                       │      React UI        │
                       └──────────┬───────────┘
                                  │
                                  ▼
                       ┌──────────────────────┐
                       │     FastAPI API      │
                       │ JWT / RBAC / Tenant  │
                       └───────┬───────┬──────┘
                               │       │
                    upload/job │       │ query
                               ▼       ▼
                       ┌──────────┐  ┌───────────┐
                       │  Redis   │  │ PostgreSQL│
                       │ Queue/DLQ│  │ + pgvector│
                       └────┬─────┘  └─────┬─────┘
                            │              │
                            ▼              │
                       ┌──────────┐       │
                       │ Workers  │       │
                       └────┬─────┘       │
                            ▼              │
                    ┌────────────────┐     │
                    │    LangGraph   │─────┘
                    │ Orchestration  │
                    └───┬────┬───┬───┘
                        │    │   │
                        ▼    ▼   ▼
                     Parser LLM RAG
                        │    │   │
                        └────┴───┘
                             │
                             ▼
                      Deterministic
                        Validation
                             │
                  ┌──────────┴──────────┐
                  │                     │
                  ▼                     ▼
             Auto Approve          Human Review
                  │                     │
                  └──────────┬──────────┘
                             ▼
                       ERP Service
                             │
                             ▼
                        Audit Trail

                    OTel + Prometheus
```

---

# Agent Implementation Order

Use this exact order.

## Phase 1 — Safety

```text
1. Real parser/OCR
2. Remove fabricated fallbacks
3. Fix registration privilege escalation
4. Remove hardcoded credentials
5. Centralize ERP side effects
6. Revalidate reviewer edits
7. Add idempotency + DB uniqueness
```

## Phase 2 — Reliability

```text
8. Redis durable queue
9. Persistent workflow/restart recovery
10. Storage abstraction + S3/MinIO
11. MIME/content validation
12. Decimal financial math
13. Explicit state machine
```

## Phase 3 — AI quality

```text
14. pgvector
15. Better RAG retrieval metrics
16. Real extraction metrics
17. True live end-to-end eval
18. Real token/cost telemetry
19. Actual latency instrumentation
```

## Phase 4 — Platform depth

```text
20. OTel end-to-end
21. Production metrics
22. Structured logs
23. Rate limiting
24. Security regression matrix
25. CI/release quality gates
26. Container/tool pinning
```

## Phase 5 — Documentation

```text
27. Correct README claims
28. Add implementation status
29. Separate measured/estimated/simulated numbers
30. Add final architecture diagram
31. Add reproducible demo scenarios
32. Add failure-mode documentation
```

---

# Definition of Done

OpsPilot should only be presented as portfolio-ready after these conditions hold:

### Security

- [ ] No public self-service admin creation
- [ ] No hardcoded passwords in app/frontend source
- [ ] Production secret validation exists
- [ ] JWT validation is strict
- [ ] Cross-tenant access is denied
- [ ] High-risk actions are permission-gated
- [ ] Reviewer edits cannot bypass deterministic validation

### Document processing

- [ ] PDF parsing works
- [ ] OCR works for scanned documents
- [ ] DOCX parsing works
- [ ] Image OCR works
- [ ] Corrupt files fail closed
- [ ] No fabricated fallback document content exists

### Workflow

- [ ] Redis-backed durable queue
- [ ] retries
- [ ] DLQ
- [ ] idempotency
- [ ] restart recovery
- [ ] explicit state transitions

### AI/RAG

- [ ] real provider-backed embeddings
- [ ] pgvector retrieval
- [ ] ACL-aware semantic retrieval
- [ ] citation correctness evaluation
- [ ] live end-to-end LLM evaluation
- [ ] actual usage telemetry

### Business controls

- [ ] Decimal financial math
- [ ] exact tolerance policy
- [ ] duplicate prevention at service + DB level
- [ ] centralized ERP posting service
- [ ] human review revalidation

### Operations

- [ ] real latency metrics
- [ ] real token/cost metrics
- [ ] OTel spans
- [ ] structured logs
- [ ] queue metrics
- [ ] failure metrics

### CI/CD

- [ ] `uv sync --frozen`
- [ ] pytest
- [ ] ruff
- [ ] mypy or equivalent type validation
- [ ] frontend build
- [ ] security/dependency scanning
- [ ] deterministic regression evaluation gate

### Documentation

- [ ] README claims match implementation
- [ ] no fake `Production Ready` labels
- [ ] benchmark methodology matches executable code
- [ ] measured vs estimated clearly separated
- [ ] deployment claims are backed by actual tested environments

---

# Final Portfolio Positioning

Once the above is complete, the project should be described as:

> **OpsPilot AI is an enterprise document-agent platform that combines multimodal document ingestion, LLM-based structured extraction, deterministic financial validation, policy-aware RAG, LangGraph orchestration, human approval workflows, multi-tenant RBAC, durable asynchronous processing, observability, and auditable ERP actions.**

The strongest interview message is not “I built an invoice bot.” It is:

> **I designed a production-oriented AI workflow where probabilistic models handle unstructured reasoning, while deterministic services control authorization, financial validation, state transitions, and irreversible side effects.**

That is the engineering story worth demonstrating.
