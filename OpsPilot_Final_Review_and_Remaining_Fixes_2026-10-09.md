# OpsPilot AI — Final Review and Remaining Fixes
**Audit date:** 2026-10-09  
**Repository:** https://github.com/VNT1998/opspilot-ai  
**Audited `main` commit:** `9a79a17dee666fe358292ede9ebc57cc2777037c`

## Verdict

**Good portfolio/demo project; not yet production-grade.** The latest GitHub Actions run succeeded for the backend tests/evaluation and frontend build. Important gaps remain in Redis queue crash recovery, invoice edit validation, and transaction consistency.

Latest CI run: https://github.com/VNT1998/opspilot-ai/actions/runs/37847853900

# Part B — OpsPilot AI: required remaining fixes

## OPS-001 — P0: Redis queue is not crash-safe despite the “durable” label

**Files:** `backend/app/services/queue/redis.py`, `backend/app/services/queue/worker.py`, `backend/app/services/queue/base.py`, `backend/tests/test_queue_durability.py`, `backend/app/api/v1/documents.py`.

**Observed:** `RedisQueueBackend.dequeue()` uses `BLPOP`, which removes a message before processing completes. If the worker dies after popping and before completing the workflow, there is no acknowledgement/reclaim mechanism to redeliver it. Current tests only verify in-memory enqueue/dequeue/DLQ and Redis key names/configuration; they do not test recovery after a worker crash.

The upload route also commits the Document row, then enqueues in a separate operation. If queue enqueue fails after the DB commit, a document can remain queued without a job.

**Implementation:**
1. Replace Redis list/`BLPOP` with Redis Streams consumer groups (preferred) or another queue with unacknowledged in-flight jobs, acknowledgement, retry, and reclaim semantics.
2. Acknowledge only after processing state is persisted.
3. Reclaim messages pending for dead consumers on recovery.
4. Persist retry metadata and DLQ failure reasons. Schedule retry through the queue rather than sleeping in the worker and occupying its capacity.
5. Implement a DB outbox or equivalent reliable dispatch/compensation so Document/WorkflowRun creation cannot silently diverge from job delivery.
6. Make job execution idempotent at workflow/resource boundaries.
7. Configure/document Redis persistence assumptions for deployment.

**Required integration tests:** worker dies after receipt and job is reclaimed; queue unavailable and dispatch is recovered; two workers do not process the same active job concurrently; retries do not block other work; exhausted retries reach persistent DLQ; Redis-backed behavior is exercised by a Redis test service rather than only a constructor test.

## OPS-002 — P0: Production can still select the in-memory queue via `WORKER_MODE`

**Files:** `backend/app/core/config.py`, `backend/app/services/queue/worker.py`, `backend/tests/test_production_config.py`.

**Observed:** Production validation rejects `USE_IN_MEMORY_QUEUE=True`, but the worker selects the in-memory backend when either that flag is true **or** `WORKER_MODE == "in_process"`. `WORKER_MODE` defaults to `in_process`, and production validation does not reject that default. Production could set `USE_IN_MEMORY_QUEUE=false`, leave `WORKER_MODE=in_process`, pass the current validator, and still instantiate the in-memory backend.

**Implementation:**
1. In production, require `WORKER_MODE == "redis"` and `USE_IN_MEMORY_QUEUE is False`.
2. Validate the settings as one coherent choice, or remove the duplicate setting and keep one source of truth.
3. Test that production + `USE_IN_MEMORY_QUEUE=false` + `WORKER_MODE=in_process` fails.
4. Test that valid production settings instantiate `RedisQueueBackend`.

## OPS-003 — P0: Reject edited invoice data when deterministic validation still fails

**Files:** `backend/app/api/v1/reviews.py`, `backend/app/services/validation/engine.py`, `backend/tests/test_reviewer_revalidation.py`, `backend/tests/test_review_state_machine.py`.

**Observed:** `edit_and_approve_review_task()` reruns `ValidationEngine` and persists `val_res.is_clean`/findings, but then posts the invoice to ERP and resolves the task without requiring validation to pass. An invoice can retain a PO mismatch, duplicate, math issue, low confidence, or other policy finding and still be posted after an unrelated field edit. `/approve` allows `admin`/`ops_manager` to bypass validation errors implicitly without a distinct override flag/reason.

**Implementation:**
1. Normal edit-and-approve must block ERP posting when the post-edit result is not auto-approvable, or leave the task pending/review-required with findings.
2. Reuse a single `is_auto_approvable()`/policy function so `/approve`, `/edit`, and agent auto-approval agree.
3. If manager/admin override is required, make it explicit: `override_policy=true`, mandatory reason, privileged role, audit before/after state and reason in the same transaction. The response should say “policy override,” not imply all rules passed.
4. Test low-value invoices with PO mismatch and subtotal/tax mismatch; editing an unrelated field must not cause ERP posting.
5. Continue enforcing the high-value role rule.
6. Use one source of truth for threshold: `requires_high_value_approval()` uses a module constant while config exposes `HIGH_VALUE_THRESHOLD`.

## OPS-004 — P1: Make production configuration self-consistent

**Files:** `backend/app/core/config.py`, `backend/app/main.py`, `backend/app/services/queue/worker.py`, `backend/app/services/storage/s3.py`, config tests.

1. Production must enforce `DEBUG=False`.
2. Production should require PostgreSQL rather than inheriting SQLite default.
3. Production CORS origins must be explicitly configured; reject localhost defaults outside an explicit local profile.
4. Require S3 storage and Redis queue in production, including both `WORKER_MODE=redis` and `USE_IN_MEMORY_QUEUE=False`.
5. If `DEFAULT_LLM_PROVIDER=anthropic` stays a valid value, implement a native provider. Otherwise remove it from the allowed setting until implemented. A setting should not pass configuration and fail only when a job arrives.
6. When demo seeding is enabled in development, require non-empty demo passwords; do not seed users with empty passwords.
7. Keep production startup free from `create_all()` and demo seed calls; continue using Alembic migrations.

## OPS-005 — P1: Use per-call provider usage and model-specific pricing

**Files:** `backend/app/services/llm/base.py`, `backend/app/services/llm/openai_provider.py`, `backend/app/services/llm/mock_provider.py`, `backend/app/services/agents/graph.py`, `backend/app/models/workflow.py`, metrics/evaluation tests.

**Observed:** Provider usage is stored in mutable `self.last_usage`. The graph calculates cost using one fixed rate for total tokens (`tokens / 1000 * 0.0015`) rather than separate input/output rates for the actual model. The graph reads `usage_source` from an attribute that may not exist even when `last_usage` says provider-backed usage. RAG generation/embedding usage is not accumulated consistently.

**Implementation:**
1. Return a typed per-call provider result with output, provider/model, input tokens, output tokens, usage source, latency, and cost attribution.
2. Remove mutable “last usage” as the join key between calls and telemetry.
3. Add central model pricing keyed by provider/model, with separate input/output token rates.
4. Track classification, extraction, generation, and embedding usage where available.
5. Mark mock/local usage estimated or unavailable; do not present it as actual cloud billing.
6. Test usage-source propagation through graph state, `AgentRun`, `ToolCall`, and metrics.

## OPS-006 — P1: Make ERP writes, review state, and audit records one transaction

**Files:** `backend/app/services/erp/service.py`, `backend/app/services/audit/service.py`, `backend/app/api/v1/reviews.py`, ERP/review tests.

**Observed:** `AuditService.log_event()` defaults to `commit=True`. `ERPService.post_invoice()` calls it while the review handler is in a larger operation. This can commit the invoice/audit and pending review changes before later workflow state/route-level audit writes have occurred. Failures afterward can leave partial business state.

**Implementation:**
1. Make the request/service boundary own the transaction. Service methods should normally `flush()` and add audit rows without committing the entire session.
2. Use `commit=False` when audit logging is part of a larger unit of work.
3. Commit only after invoice, extraction, review action, document state, workflow state, and audit records are all written successfully.
4. Ensure rollback leaves none of those side effects persisted if any step fails.
5. Enforce idempotency for `(tenant_id, document_id)` with a DB unique constraint/index, not only a pre-insert SELECT. Keep the `(tenant_id, invoice_number)` uniqueness constraint.
6. Test rollback after ERP flush, before workflow update, and during audit creation.

## OPS-007 — P1: Add reliable dispatch/outbox semantics for document ingestion

**Files:** `backend/app/api/v1/documents.py`, `backend/app/services/queue/worker.py`, `backend/app/models/workflow.py`, outbox model/migration if used.

1. If job dispatch fails, do not return success while a document has no corresponding job.
2. Persist an outbox/dispatch-pending row in the same DB transaction as Document and WorkflowRun.
3. Dispatcher retries unsent outbox rows and records dispatch attempts/errors.
4. If accepted into a durable outbox, 202 is valid; status should expose pending dispatch. Do not leave a permanently `QUEUED` document with no dispatch record.
5. Make reprocess idempotent and prevent concurrent duplicate runs.
6. Add integration tests for Redis unavailable, enqueue failure, duplicate reprocess, and recovery.

## OPS-008 — P1: Preserve original-document security findings through human review

**Files:** `backend/app/api/v1/reviews.py`, `backend/app/services/validation/engine.py`, audit service, prompt-injection tests.

**Observed:** Agent validation receives `raw_text`, but `/approve` and `/edit` re-run validation without it. Revalidation during review therefore lacks the original-document text that the injection detector scans.

**Implementation:**
1. Load persisted page text or a persisted risk/finding record and include it when revalidating `/approve` and `/edit`.
2. Do not let edited extracted fields silently erase an existing critical security finding.
3. If a human can proceed after an injection finding, require explicit acknowledgement/reason and audit it.
4. Document injection scanning as a deterministic regression guard, not a guarantee against every possible prompt injection attack.
5. Test that the finding survives edits and that any allowed override is auditable.

## OPS-009 — P1: Align canonical PO tolerance text everywhere

**Files:** `backend/app/main.py` (seeded RAG policy), `backend/app/services/validation/policies.py`, validation engine, eval methodology, README, tests.

**Observed:** The deterministic rule enforces `variance_percent <= 2.00% AND variance_amount <= $5.00`, but seeded policy text still says “2.0% or $5.00”.

**Implementation:** Choose one canonical policy. The current code implements AND; update seed content, evaluation expected outcomes, README, methodology, and frontend explanations to match. If OR is the intended business policy instead, change code and all tests/docs consistently. Add boundaries where percent passes but amount fails; amount passes but percent fails; both pass; both fail.

## OPS-010 — P1: Correct 3-way-matching and immutable-audit claims

**Files:** `README.md`, `backend/app/main.py`, `backend/app/models/erp.py`, `backend/app/models/audit.py`, audit tests.

**Observed:** Current models have Purchase Orders and Invoices but no Goods Receipt entity, so implemented matching is invoice-to-PO, not true PO + receipt + invoice 3-way matching. The audit is hash-chained, but application hashing alone does not make database rows immutable. The event hash does not cover every security-relevant audit field, and concurrent writers may read the same previous hash and create chain forks.

**Implementation:**
1. Until receipt matching exists, change README/seed terminology to “invoice-to-PO matching.” A later enhancement can add `GoodsReceipt`/`GoodsReceiptLine` and migrations.
2. Hash a canonical payload containing actor/user, actor type, tenant, action, resource, reason, request/workflow IDs, before/after state, timestamp, and previous hash.
3. Serialize chain append per tenant (DB lock/advisory lock or another safe mechanism).
4. Add a verifier and tests. If DB update/delete are not prevented, describe it as an append-oriented hash-chained log, not an immutable ledger.

## OPS-011 — P1: Make rate limiting shared across production replicas

**Files:** `backend/app/core/rate_limit.py`, auth/documents/knowledge routes, tests.

**Observed:** Rate limiting is now attached to several routes, but state lives in a process-local dictionary. Each API replica has independent limits, and local history has no clear size/cleanup strategy for inactive keys.

**Implementation:** Keep local limiter for development/test. Use Redis-backed atomic rate limiting in production. Trust forwarded client IP only behind a configured trusted proxy. Add TTL/cleanup for local mode and a test proving multiple limiter instances share production quotas.

## OPS-012 — P2: Make OCR behavior reproducible and accurately described

**Files:** PDF/image parser, `backend/pyproject.toml`, README, parser tests.

1. The PDF parser extracts embedded text; scanned PDFs without a text layer must go to OCR or be marked manual-review-required.
2. Document and install the OCR runtime dependencies for image OCR; do not claim OCR is verified when the engine is unavailable.
3. Distinguish measured OCR confidence from a heuristic confidence estimate.
4. Align allowed upload extensions, content sniffing, actual parser support, and README.
5. Add a real OCR integration test, or describe scan OCR as optional/external.

## OPS-013 — P2: Keep README claims aligned with evidence

**Files:** `README.md`, `evals/METHODOLOGY.md`, `evals/reports/EVAL_REPORT.md`.

1. Correct 3-way matching to invoice-to-PO matching unless receipt entities are implemented.
2. Do not say “immutable audit log” without database-level immutability controls.
3. Only call the Redis queue durable after crash recovery/acknowledgement tests prove it.
4. Limit injection claims to the tested attack corpus; do not generalize a finite regex benchmark into universal security.
5. Preserve measured/calculated/estimated labels. Cloud cost is estimated where usage/pricing is approximate.
6. Make test counts match the actual test collection and CI results.

---

## Execution order for OpsPilot AI

1. Implement Redis acknowledgement/recovery semantics and guarantee production selects the Redis queue.
2. Block ERP posting when post-edit deterministic validation still fails; make any override explicit.
3. Harden production configuration.
4. Correct transaction ownership and add reliable dispatch/outbox handling.
5. Implement per-call provider usage and model-specific estimated pricing.
6. Preserve original document risk findings through review and align tolerance policy text.
7. Strengthen audit-chain integrity and use shared production rate limiting.
8. Correct OCR behavior and documentation accuracy.

## Verification commands

From the repository root:

```bash
cd backend
uv sync --frozen --all-groups
uv run ruff check .
uv run ruff format --check .
uv run alembic upgrade head
uv run pytest -v
uv run python ../evals/scripts/run_evals.py --mode=regression
cd ../frontend
npm ci
npm run build
```

Add a Redis service to CI and run integration tests for:
- Worker crash after message receipt.
- Pending-message reclaim.
- Duplicate worker execution.
- Enqueue outage/outbox recovery.
- Persistent DLQ.
- Explicit production queue selection.
- Failed invoice edit revalidation never posting to ERP.
- Transaction rollback across invoice/review/workflow/audit writes.

## Definition of done

OpsPilot is a good portfolio/demo foundation, and the latest reported CI run is green. Do not describe it as production-grade until the Redis queue demonstrates acknowledgement/recovery semantics, invalid edited invoices cannot be posted without an explicit policy override, and transaction/audit behavior is corrected.

A feature is complete only when it exists in code, is used by the real execution path, has a test that proves the failure mode, and is documented accurately.

---

# Part E — Service plan for your existing self-hosted infrastructure

## Available services: Supabase and Redis

### 1. Supabase PostgreSQL — use it

OpsPilot's ORM uses SQLAlchemy and `asyncpg`, so its database can use self-hosted Supabase PostgreSQL directly. Configure a separate database or schema/role from Nuvorix:

```env
DATABASE_URL=postgresql+asyncpg://<opspilot_db_user>:<password>@<supabase-postgres-host>:5432/<opspilot_database>
```

Keep the application database user least-privileged; do not use the PostgreSQL superuser for routine application access. URL-encode special characters in the password as required by the connection URL. Keep the database on a trusted private network/VPN or secure it with TLS.

The app uses direct SQLAlchemy database access, so its `DATABASE_URL` is what matters. Supabase REST URL and API keys do not replace this SQL connection.

### 2. Redis — required for the intended production queue

Use your existing Redis server; **no separate queue service is needed**. Configure:

```env
REDIS_URL=redis://<redis-host>:6379/<database-number>
USE_IN_MEMORY_QUEUE=false
WORKER_MODE=redis
```

Use the actual authenticated URL format supported by your Redis configuration. Keep Redis private, enable ACL/authentication, and configure persistence appropriate to your risk tolerance (for example, AOF plus a tested backup/recovery plan).

**The code still needs to change.** Current `RedisQueueBackend.dequeue()` uses `BLPOP`, which removes a job from the list before the worker finishes. If the worker dies after the pop, Redis alone cannot redeliver that in-flight job. The fix specification's Redis Streams/consumer-group acknowledgement and reclaim work is still required. Do not mark the queue durable solely because `REDIS_URL` points to a running server.

Production configuration also needs to reject `WORKER_MODE=in_process`; otherwise the worker can still select the in-memory backend even when `USE_IN_MEMORY_QUEUE=false`.

### 3. Document storage — Supabase Storage may remove the need for a separate object-store service

OpsPilot's production configuration expects S3-compatible storage. You can test your self-hosted Supabase Storage S3 endpoint before adding another service.

Official self-hosted Supabase guide: https://supabase.com/docs/guides/self-hosting/self-hosted-s3

General configuration:

```env
STORAGE_TYPE=s3
S3_BUCKET_NAME=opspilot-documents
S3_REGION=<configured-supabase-storage-region>
S3_ENDPOINT_URL=https://<your-supabase-host>/storage/v1/s3
AWS_ACCESS_KEY_ID=<server-side-s3-access-key-id>
AWS_SECRET_ACCESS_KEY=<server-side-s3-secret-access-key>
```

Actions required:
1. Enable the S3 protocol endpoint in your self-hosted Supabase Storage configuration.
2. Create the `opspilot-documents` bucket.
3. Use the exact S3 protocol credentials and region from your Supabase deployment.
4. Configure boto3 for the endpoint's correct addressing style (including path-style addressing if required by your endpoint).
5. Test `put_object`, `get_object`, and `delete_object` against the real self-hosted instance.
6. Verify the configured Supabase Storage backend persists files across container recreation. The S3-compatible API endpoint and the storage backend are separate configuration choices.

Supabase's S3 access keys are privileged server-side credentials; never place them in frontend code or commit them. If the S3 endpoint or persistence behavior does not meet the app's requirements, self-host a dedicated S3-compatible object store such as RustFS. Do not deploy a second object store until the Supabase option has been tested.

### 4. LLM provider — choose hosted API or self-hosted inference

OpsPilot needs a real inference provider for meaningful live document classification/extraction. A working Supabase and Redis setup does not supply an LLM.

The current `OpenAIProvider` hardcodes `https://api.openai.com/v1`. For hosted OpenAI, set:

```env
DEFAULT_LLM_PROVIDER=openai
OPENAI_API_KEY=<secret>
OPENAI_MODEL=<model-available-to-your-account>
```

If you prefer self-hosted Ollama or vLLM:
1. Add a configurable `OPENAI_BASE_URL` to the provider implementation.
2. Use the OpenAI-compatible endpoint for the selected self-hosted model.
3. Ensure the production provider factory selects this provider and fails clearly on connectivity/model errors.
4. Do not silently fall back to `MockLLMProvider`.
5. Remove `anthropic` from accepted config until a real Anthropic adapter is implemented, or implement and test that adapter.

No additional LLM server is necessary if you're comfortable using a hosted provider/API key; self-hosting inference is optional.

### 5. MLflow — not required for OpsPilot

OpsPilot's current workflow does not need an MLflow Tracking Server to fix the issues in its file. Do not add MLflow to the deployment just because Nuvorix uses it.

### 6. Observability — optional

A Prometheus/Grafana and OpenTelemetry Collector/trace backend are useful for a stronger deployment demonstration but are not prerequisites for closing the P0 bugs. Add them only after Redis recovery, database, object storage, provider, and review transaction correctness are verified.

## OpsPilot service verdict

**Your existing Supabase and Redis are enough to start implementing and testing the main fixes.** For a realistic production-like run, use:
1. Supabase PostgreSQL.
2. Redis with persistence and the corrected acknowledgement/recovery queue implementation.
3. A real LLM provider (hosted API or self-hosted OpenAI-compatible endpoint).
4. Supabase Storage via its S3-compatible endpoint, if integration tests pass; otherwise add a dedicated S3-compatible store.

You do not need another queue product, a separate PostgreSQL server, or MLflow for OpsPilot at this stage. Keep secrets out of chat/source control and inject them through deployment environment secrets.

---

## Part F — Concrete endpoint mapping from the latest configuration

Sensitive values are intentionally not copied into this review. Inject them through your deployment secret manager or environment file.

### Supabase

Your supplied Supabase API URL is `https://api-supabase.calmalpha.in`. `SUPABASE_URL` and `SUPABASE_KEY` can serve code paths using Supabase's HTTP client/auth, but they **do not replace the PostgreSQL connection URI** used by the app's SQLAlchemy/asyncpg database layer. Set the database connection variable that the current OpsPilot settings actually read to your self-hosted PostgreSQL connection URI, disable SQLite for production, run migrations, and use a dedicated database role. Production must not silently run with an in-memory database/store if the DB URI is missing.

### Redis — required for the intended production queue, after reliability fixes

The Redis host/port supplied are `100.101.158.48:8086`. Configure the exact Redis URL/host/password variable the app reads; when using a URI, URL-encode reserved characters in the password. Use `rediss://` only if TLS is enabled. Ensure the OpsPilot runtime and worker can route to `100.101.158.48` (it is inside the shared `100.64.0.0/10` address range, commonly used by private overlay networks). Keep Redis private and authenticated, with persistence/backup configured. **Do not treat Redis as production-safe until the `BLPOP` job-loss issue is fixed** using acknowledgement and pending-message recovery (or an equivalent reliable queue design), and add recovery tests.

### Ollama — requires a provider code change in OpsPilot

The supplied Ollama endpoint is `https://ollama.calmalpha.in/`. For an OpenAI-compatible client, the base URL is normally `https://ollama.calmalpha.in/v1`, provided the reverse proxy exposes that route. Configure `medgemma:4b` as the primary model and the supplied fallbacks only after checking that each is actually available from the endpoint.

The current OpsPilot `OpenAIProvider` hardcodes `https://api.openai.com/v1`; the supplied `OLLAMA_BASE_URL`, `OLLAMA_PRIMARY_MODEL`, and `OLLAMA_FALLBACK_MODELS` variables will not work until the provider and settings/factory read them. Implement a configurable base URL and primary/fallback selection, then test timeout, unreachable endpoint, unknown model, fallback, and no-silent-mock-fallback behavior. The public Ollama library lists `medgemma:4b`, `phi4-mini:latest`, and `granite4.1:3b`. `qwen3.5:4b-mlx` is an MLX variant: verify compatibility with the host behind the endpoint, and consider a standard Linux Ollama tag such as `qwen3.5:4b-q4_K_M` if needed.

### Security and operational checks

- Your Redis password appeared in chat. Rotate it, then update the deployment secret. Avoid command-line `-a <password>` where it could be recorded in shell history/process listings; use a safer secret injection method or interactive prompt.
- A Supabase `anon` key is designed for client use, but it is not a database password. Ensure Row Level Security is enabled for exposed tables and policies are correct. Never substitute a `service_role` key in frontend code.
- Before calling this production-ready, verify Postgres connectivity/migrations, Redis queue recovery, real Ollama inference, and Supabase Storage S3-compatible upload/download/delete if using it for documents. MLflow is not required for OpsPilot.

### Readiness summary

Your existing Supabase, Redis, and Ollama services are sufficient to avoid adding separate Postgres, queue, or LLM services. They are **not yet plug-and-play with the current OpsPilot code**: set the Postgres URI, correct the queue reliability, and add configurable Ollama provider support before the production-like deployment test.
