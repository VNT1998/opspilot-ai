# OpsPilot AI — Evaluation Benchmark Methodology

## 1. Overview & Objective

OpsPilot AI evaluates autonomous enterprise operations using a dual-track testing philosophy:
1. **Deterministic System Boundaries:** Business rules, invoice-to-PO matching, Decimal arithmetic balance checks, and security access controls are verified with 100% mathematical certainty in code, never delegated to probabilistic LLM inference.
2. **Probabilistic AI Capabilities:** Document classification, multi-page semi-structured field extraction, semantic vector search, and citation grounding are evaluated against labeled enterprise financial documents.

This document details the metric classifications (MEASURED vs CALCULATED vs ESTIMATED), dataset taxonomy, mathematical formulas, evaluation modes, edge cases, and reproducibility protocols for OpsPilot AI.

---

## 2. Metric Classification Standard

To maintain strict truthfulness and prevent confusion between direct observations and synthetic projections, every benchmark metric is explicitly assigned to one of three categories:

### [MEASURED]
Direct automated observations and code-enforced assertions recorded during runtime execution:
- **Classification Accuracy:** Direct categorical equality between predicted and ground-truth document types.
- **Field Extraction Exact Match:** Exact string equality for invoice number and $\le \$0.10$ absolute numerical difference for total amount.
- **Workflow Decision Accuracy:** Exact state equality for routing outcomes (`AUTO_APPROVE` vs `SEND_TO_REVIEW`).
- **Prompt Injection Defense Rate:** Empirical assertion that adversarial inputs fail auto-approval gates and route to `SEND_TO_REVIEW`.
- **RAG Recall@2 & MRR@2:** Empirical presence and reciprocal rank of target policy documents in the top-2 retrieved knowledge chunks.
- **Engine Latency:** Measured wall-clock time from test case input receipt to completion.
- **Provider Token Usage (Live Mode):** Direct token usage reported by cloud LLM provider API responses.

### [CALCULATED]
Values derived mathematically from measured values using deterministic formulas:
- **Live Provider Cost:** Multiplied measured provider input/output tokens by centralized static pricing schedules (e.g. OpenAI `gpt-4o-mini` at $0.15/1M input tokens, $0.60/1M output tokens).
- **Mean Reciprocal Rank (MRR):** Harmonic mean of the retrieval ranks across all search evaluation queries.
- **Variance Percentage:** Calculated Decimal ratio between invoice amount and PO total amount.

### [ESTIMATED]
Explicit estimations when live provider measurements are unavailable (e.g., in offline or deterministic mock mode):
- **Mock Token Usage:** Fixed heuristic token allocations tagged `usage_source = "estimated"`.
- **Mock Cost:** Cost derived from estimated tokens, labeled `(ESTIMATED)`.

---

## 3. Dataset Taxonomy & Categories (v2.0)

The benchmark suite consists of **55 labeled enterprise documents** (`evals/datasets/benchmark_cases.json`) categorized into six operational scenarios:

| Category | Cases | Operational Characteristics & Failure Scenarios Tested |
|---|:---:|---|
| `clean_standard` | 20 | Clean vendor invoices with matching PO numbers, matching totals within corporate tolerance ($1,449.10 – $1,450.90 vs PO-9001 of $1,450.00), valid dates, and compliant tax calculations. Qualifies for **Straight-Through Processing (STP)**. |
| `po_variance_exceeded` | 10 | Pricing discrepancies, shipping surcharges, or quantity variances exceeding the $5.00 or 2.0% corporate variance tolerance threshold. Flagged and routed to the **Human Review Queue**. |
| `high_value_policy` | 8 | Large invoices exceeding the $10,000 threshold (e.g. $12,500 – $48,000). Regardless of PO match accuracy, corporate governance SOP-FIN-2026 mandates **Operations Manager sign-off**. |
| `poor_scan_quality` | 6 | Degraded scan artifacts, faint dot-matrix printing, or blurry OCR with field confidence levels dropping below 85%. Triggers low-confidence review flags. |
| `math_discrepancy` | 4 | Invoices where $\text{Subtotal} + \text{Tax} \neq \text{Total Amount Due}$ due to vendor billing errors or rounding discrepancies $> \$0.05$. Stopped before ERP posting. |
| `adversarial_prompt_injection` | 7 | Untrusted instructions embedded in invoice text attempting to bypass validation, spoof SYSTEM roles, escalate privileges, or skip matching rules. Includes clean low-value invoices that otherwise match PO totals (`tc_inject_clean_001` - `005`). Must be caught by deterministic policy defenses and routed to **SEND_TO_REVIEW**. |

---

## 4. Metric Definitions & Mathematical Formulas

### 4.1 Document Classification Accuracy [MEASURED]
$$\text{Accuracy}_{\text{classification}} = \frac{\sum_{i=1}^N \mathbb{I}(\hat{y}_i = y_i)}{N} \times 100$$
Where $\hat{y}_i \in \{\text{invoice}, \text{purchase\_order}, \text{contract}, \text{receipt}, \text{other}\}$ and $N = 55$.

### 4.2 Field Extraction Exact Match [MEASURED]
$$\text{Match}_{\text{field}} = \mathbb{I}(\hat{\text{inv\_num}} = \text{inv\_num}^*) \wedge \mathbb{I}(|\hat{\text{total}} - \text{total}^*| \le 0.10)$$
$$\text{Accuracy}_{\text{extraction}} = \frac{\sum_{i=1}^N \text{Match}_{\text{field}, i}}{N} \times 100$$

### 4.3 Purchase Order Variance Calculation [CALCULATED]
Invoice-to-PO matching between invoice line totals and approved ERP purchase orders:
$$\text{Variance}_{\%} = \frac{|\text{Total}_{\text{invoice}} - \text{Total}_{\text{PO}}|}{\text{Total}_{\text{PO}}} \times 100$$
$$\text{Delta}_{\$} = |\text{Total}_{\text{invoice}} - \text{Total}_{\text{PO}}|$$

**Auto-Approval Boundary:**
$$\text{PO\_Compliant} \iff \text{Variance}_{\%} \le 2.0\% \quad \text{AND} \quad \text{Delta}_{\$} \le \$5.00$$

### 4.4 Arithmetic Line Consistency [MEASURED]
Verifies that individual subcomponents sum up correctly within Decimal precision tolerance:
$$|\text{Total} - (\text{Subtotal} + \text{Tax})| \le \$0.05$$

### 4.5 RAG Recall@K & MRR@K [MEASURED & CALCULATED]
Evaluates whether policy retrieval queries return verifiable citations pointing directly to indexed corporate policies within the top-$K$ results ($K = 2$):
$$\text{Recall@K} = \frac{\sum_{q=1}^Q \mathbb{I}(\text{TargetDoc} \in \text{TopK}_q)}{Q} \times 100$$
$$\text{MRR@K} = \frac{1}{Q} \sum_{q=1}^Q \frac{1}{\text{rank}_q}$$
Where $\text{rank}_q$ is the 1-based index of the first relevant result in top-$K$, or 0 if not retrieved.

Every citation response schema guarantees full provenance:
- `document_id`: UUID of parent indexed SOP document
- `chunk_id`: Unique identifier of text chunk
- `page_number`: Original document page number
- `snippet`: Extracted policy passage
- `relevance_score`: Dense cosine similarity + lexical keyword hybrid score

### 4.6 Prompt Injection Defense Rate [MEASURED]
Measures resilience against prompt manipulation attempts inside untrusted document text:
$$\text{Defense}_{\text{injection}} = \frac{\sum_{k=1}^K \mathbb{I}(\text{Outcome}_k = \text{"SEND\_TO\_REVIEW"})}{K} \times 100$$
Target: **100.0%**. Documents containing injection payloads must never achieve automated straight-through execution.

---

## 5. Evaluation Modes & Latency Disentanglement

OpsPilot AI provides dual evaluation modes to clearly distinguish **in-memory deterministic engine benchmarks** from **live cloud model roundtrips**:

```text
┌────────────────────────────────────────────────────────┐
│                   OpsPilot Benchmark                   │
└───────────────────────────┬────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
    --mode=regression                 --mode=live
   (Deterministic Mock)             (Live OpenAI API)
            │                               │
  • In-memory DB & embeddings     • OpenAI gpt-4o-mini
  • Local validation engine       • text-embedding-3-small
  • CI/CD automated gates         • Live API roundtrips
  • Sub-millisecond latency       • 800–2,200ms latency
  • Estimated usage labeling      • Provider-reported usage
```

### 5.1 Mode: `--mode=regression` (Default)
- **Engine:** Deterministic `MockLLMProvider` using compiled regex parsing, deterministic field extraction, and in-memory cosine vector similarity.
- **Latency Profile:** **0.70 ms – 1.20 ms** per document (MEASURED local execution time).
- **Purpose:** Verifies that deterministic business rules, tolerance boundaries, high-value checks, and RAG schemas do not regress during development or CI/CD runs.
- **Dependencies:** Fully offline, zero external API keys required.

### 5.2 Mode: `--mode=live`
- **Engine:** `OpenAIProvider` calling OpenAI's Chat Completions (`gpt-4o-mini` with JSON schema enforcement) and Embeddings API (`text-embedding-3-small`).
- **Latency Profile:** **800 ms – 2,200 ms** per document (MEASURED live roundtrip time).
- **Purpose:** Measures end-to-end cloud model extraction fidelity, OCR transcription resilience, and real API token costs.
- **Dependencies:** Requires valid `OPENAI_API_KEY`.

---

## 6. Security & Multi-Tenant Boundary Isolation

OpsPilot AI enforces strict multi-tenant boundaries at the database ORM query level:
1. **Tenant Isolation:** Every SQL query includes an explicit `where(Entity.tenant_id == current_user.tenant_id)` clause.
2. **Access Control Lists (ACL):** Knowledge base chunks and policies require matching caller roles (`admin`, `ops_manager`, `reviewer`, `viewer`).
3. **No Cross-Tenant Information Leaks:** As verified by `test_security_multitenancy.py`, requesting cross-tenant document IDs, review tasks, or RAG searches returns HTTP 404 (or 0 results), preventing side-channel data leakage.

---

## 7. How to Reproduce Benchmark Results

### Local Deterministic Regression Benchmark:
```bash
cd backend
uv run python ../evals/scripts/run_evals.py --mode=regression
```

### Live Cloud LLM Benchmark:
```bash
export OPENAI_API_KEY="sk-..."
cd backend
uv run python ../evals/scripts/run_evals.py --mode=live
```

Reports are automatically generated and saved to:
- `evals/reports/eval_results.json` (Structured JSON with per-case telemetry and metric types)
- `evals/reports/EVAL_REPORT.md` (Human-readable Markdown KPI audit report)
