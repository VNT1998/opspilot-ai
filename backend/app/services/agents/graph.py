import json
import time
from typing import Dict
from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.document import Document
from app.models.extraction import DocumentExtraction
from app.models.workflow import AgentRun, ToolCall, WorkflowRun, WorkflowStep
from app.schemas.extraction import InvoiceExtractionSchema
from app.services.agents.state import OpsPilotState
from app.services.llm.base import LLMProvider
from app.services.rag.engine import RAGEngine
from app.services.tools.definitions import (
    CreateReviewTaskInput,
    ToolCallContext,
)
from app.services.tools.registry import ToolRegistry
from app.services.validation.engine import ValidationEngine


class AgentWorkflowService:
    """
    Stateful LangGraph Agent Orchestrator combining AI classification,
    structured extraction, deterministic business rules, RAG policy lookup,
    allowlisted tool calls, and human review routing.
    """

    def __init__(self, db: AsyncSession, llm_provider: LLMProvider):
        self.db = db
        self.llm = llm_provider
        self.validator = ValidationEngine(db)
        self.rag = RAGEngine(db, llm_provider)
        self.tools = ToolRegistry(db, llm_provider)

    async def _record_step(
        self,
        workflow_run_id: str,
        tenant_id: str,
        step_name: str,
        status: str,
        input_state: Dict,
        output_state: Dict,
        latency_ms: int,
    ):
        step = WorkflowStep(
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
            step_name=step_name,
            status=status,
            input_state=json.dumps(input_state, default=str),
            output_state=json.dumps(output_state, default=str),
            latency_ms=latency_ms,
        )
        self.db.add(step)
        await self.db.flush()

    def build_graph(self):
        workflow = StateGraph(OpsPilotState)

        # 1. Intake Node
        async def intake_node(state: OpsPilotState) -> Dict:
            start_t = time.time()
            logs = list(state.get("logs", []))
            logs.append(f"Intake: Initiating processing for document '{state.get('filename')}'")
            out = {
                "logs": logs,
                "tool_calls_executed": state.get("tool_calls_executed", []),
                "total_tokens": state.get("total_tokens", 0),
                "total_cost": state.get("total_cost", 0.0),
                "usage_source": getattr(self.llm, "usage_source", "estimated"),
            }
            elapsed = int((time.time() - start_t) * 1000)
            if state.get("workflow_run_id"):
                await self._record_step(
                    state["workflow_run_id"], state["tenant_id"], "intake", "SUCCESS", state, out, elapsed
                )
            return out

        # 2. Classification Node
        async def classification_node(state: OpsPilotState) -> Dict:
            start_t = time.time()
            text = state.get("raw_text", "")
            fname = state.get("filename", "")
            cls_res = await self.llm.classify_document(text, fname)
            doc_type = cls_res.document_type if hasattr(cls_res, "document_type") else cls_res[0]
            conf = cls_res.confidence if hasattr(cls_res, "confidence") else cls_res[1]
            usage = getattr(cls_res, "usage", None)

            logs = list(state.get("logs", []))
            logs.append(f"Classification: Classified as '{doc_type}' with confidence {conf:.2f}")

            # Capture typed usage telemetry
            in_tokens = usage.input_tokens if usage else 0
            out_tokens = usage.output_tokens if usage else 0
            cost_incurred = usage.cost if usage else 0.0
            source = usage.usage_source if usage else getattr(self.llm, "usage_source", "estimated")
            model = usage.model if usage else getattr(self.llm, "model", "mock-agent-v1")
            provider = usage.provider if usage else getattr(self.llm, "provider", "mock")

            current_in = state.get("input_tokens") or 0
            current_out = state.get("output_tokens") or 0
            current_cost = state.get("total_cost") or 0.0

            total_in = current_in + in_tokens
            total_out = current_out + out_tokens
            total_cost = round(current_cost + cost_incurred, 6)

            prev_source = state.get("usage_source")
            agg_source = "provider" if (source == "provider" or prev_source == "provider") else "estimated"

            out = {
                "classification": doc_type,
                "classification_confidence": conf,
                "logs": logs,
                "model": model,
                "provider": provider,
                "input_tokens": total_in,
                "output_tokens": total_out,
                "total_tokens": total_in + total_out,
                "total_cost": total_cost,
                "usage_source": agg_source,
            }
            elapsed = int((time.time() - start_t) * 1000)
            if state.get("workflow_run_id"):
                await self._record_step(
                    state["workflow_run_id"], state["tenant_id"], "classification", "SUCCESS", state, out, elapsed
                )
            return out

        # 3. Extraction Node
        async def extraction_node(state: OpsPilotState) -> Dict:
            start_t = time.time()
            text = state.get("raw_text", "")
            ext_res = await self.llm.extract_structured(text, InvoiceExtractionSchema)
            extracted_obj = ext_res.extracted_data if hasattr(ext_res, "extracted_data") else ext_res[0]
            field_confs = ext_res.field_confidences if hasattr(ext_res, "field_confidences") else ext_res[1]
            usage = getattr(ext_res, "usage", None)

            logs = list(state.get("logs", []))
            logs.append(
                f"Extraction: Extracted invoice {extracted_obj.invoice_number} from vendor '{extracted_obj.vendor_name}'"
            )

            in_tokens = usage.input_tokens if usage else 0
            out_tokens = usage.output_tokens if usage else 0
            cost_incurred = usage.cost if usage else 0.0
            source = usage.usage_source if usage else getattr(self.llm, "usage_source", "estimated")
            model = usage.model if usage else getattr(self.llm, "model", "mock-agent-v1")
            provider = usage.provider if usage else getattr(self.llm, "provider", "mock")

            current_in = state.get("input_tokens") or 0
            current_out = state.get("output_tokens") or 0
            current_cost = state.get("total_cost") or 0.0

            total_in = current_in + in_tokens
            total_out = current_out + out_tokens
            total_cost = round(current_cost + cost_incurred, 6)

            prev_source = state.get("usage_source")
            agg_source = "provider" if (source == "provider" or prev_source == "provider") else "estimated"

            out = {
                "extracted_data": extracted_obj.model_dump(),
                "field_confidences": field_confs,
                "logs": logs,
                "model": model,
                "provider": provider,
                "input_tokens": total_in,
                "output_tokens": total_out,
                "total_tokens": total_in + total_out,
                "total_cost": total_cost,
                "usage_source": agg_source,
            }
            elapsed = int((time.time() - start_t) * 1000)
            if state.get("workflow_run_id"):
                await self._record_step(
                    state["workflow_run_id"], state["tenant_id"], "extraction", "SUCCESS", state, out, elapsed
                )
            return out

        # 4. Validation Node (Deterministic)
        async def validation_node(state: OpsPilotState) -> Dict:
            start_t = time.time()
            extracted_dict = state.get("extracted_data", {})
            field_confs = state.get("field_confidences", {})
            schema_inst = InvoiceExtractionSchema.model_validate(extracted_dict)

            val_res = await self.validator.validate_invoice(
                tenant_id=state["tenant_id"],
                extraction=schema_inst,
                field_confidences=field_confs,
                raw_text=state.get("raw_text"),
            )

            logs = list(state.get("logs", []))
            status_str = "CLEAN" if val_res.is_clean else "REQUIRES_REVIEW"
            logs.append(
                f"Validation: Deterministic check result: {status_str} (Confidence: {val_res.confidence_score})"
            )
            out = {
                "validation_result": val_res.model_dump(),
                "logs": logs,
            }
            elapsed = int((time.time() - start_t) * 1000)
            if state.get("workflow_run_id"):
                await self._record_step(
                    state["workflow_run_id"], state["tenant_id"], "validation", "SUCCESS", state, out, elapsed
                )
            return out

        # 5. RAG Policy Node
        async def rag_policy_node(state: OpsPilotState) -> Dict:
            start_t = time.time()
            extracted_dict = state.get("extracted_data", {})
            total_val = extracted_dict.get("total", 0.0)
            query = f"What is the accounts payable policy and approval threshold for invoice amount ${total_val}?"

            search_res = await self.rag.hybrid_search(
                tenant_id=state["tenant_id"],
                query=query,
                user_role=state.get("user_role", "admin"),
                limit=3,
            )

            citations_list = [c.model_dump() for c in search_res.sources]
            logs = list(state.get("logs", []))
            logs.append(f"RAG Policy Lookup: Retrieved {len(citations_list)} citations for approval policy")
            out = {
                "policy_citations": citations_list,
                "logs": logs,
            }
            elapsed = int((time.time() - start_t) * 1000)
            if state.get("workflow_run_id"):
                await self._record_step(
                    state["workflow_run_id"], state["tenant_id"], "rag_policy", "SUCCESS", state, out, elapsed
                )
            return out

        # 6. Decision Node
        async def decision_node(state: OpsPilotState) -> Dict:
            start_t = time.time()
            val_res = state.get("validation_result", {})
            requires_review = val_res.get("requires_human_review", False)
            is_clean = val_res.get("is_clean", False)
            routing_reason = val_res.get("routing_reason", "")

            logs = list(state.get("logs", []))
            if is_clean and not requires_review:
                decision = "APPROVE_AUTOMATICALLY"
                decision_reason = "Automated processing criteria fully met; all deterministic rules passed."
                logs.append(f"Decision: {decision} — {decision_reason}")
            else:
                decision = "SEND_TO_REVIEW"
                decision_reason = routing_reason or "Exception encountered during validation rules check."
                logs.append(f"Decision: {decision} — {decision_reason}")

            out = {
                "decision": decision,
                "decision_reason": decision_reason,
                "logs": logs,
            }
            elapsed = int((time.time() - start_t) * 1000)
            if state.get("workflow_run_id"):
                await self._record_step(
                    state["workflow_run_id"], state["tenant_id"], "decision", "SUCCESS", state, out, elapsed
                )
            return out

        # 7. Action Node
        async def action_node(state: OpsPilotState) -> Dict:
            start_t = time.time()
            ctx = ToolCallContext(
                tenant_id=state["tenant_id"],
                user_id=state.get("user_id") or "agent_system",
                user_role=state.get("user_role") or "reviewer",
                workflow_run_id=state.get("workflow_run_id"),
                source="agent",
            )
            decision = state.get("decision", "SEND_TO_REVIEW")
            doc_id = state["document_id"]
            logs = list(state.get("logs", []))
            tool_calls = list(state.get("tool_calls_executed", []))
            review_task_id = None
            invoice_id = None

            # Deterministic policy guard: LLM proposes, policy decides
            if decision == "APPROVE_AUTOMATICALLY":
                val_res = state.get("validation_result", {})
                if not val_res.get("is_clean", False) or val_res.get("requires_human_review", True):
                    decision = "SEND_TO_REVIEW"
                    state["decision_reason"] = (
                        val_res.get("routing_reason") or "Deterministic policy requires human review."
                    )
                    logs.append(
                        "Action Guard: Overriding APPROVE_AUTOMATICALLY to SEND_TO_REVIEW due to validation policy."
                    )

            if decision == "APPROVE_AUTOMATICALLY":
                # Create posted invoice in ERP
                t_tool_start = time.time()
                ext_dict = state.get("extracted_data", {})
                from app.services.erp.service import ERPService

                erp_service = ERPService(self.db)
                inv = await erp_service.post_invoice(
                    tenant_id=state["tenant_id"],
                    document_id=doc_id,
                    invoice_number=ext_dict.get("invoice_number", "INV-UNKNOWN"),
                    vendor_name=ext_dict.get("vendor_name", "Unknown Vendor"),
                    po_number=ext_dict.get("po_number"),
                    total_amount=ext_dict.get("total", 0.0),
                    currency=ext_dict.get("currency", "USD"),
                    source="agent",
                    actor_id=state.get("user_id", "agent_system"),
                    validation_status="CLEAN",
                )
                t_tool_elapsed = max(int((time.time() - t_tool_start) * 1000), 1)
                invoice_id = inv.id

                # Update document status
                stmt = select(Document).where(Document.id == doc_id, Document.tenant_id == state["tenant_id"])
                doc = (await self.db.execute(stmt)).scalar_one_or_none()
                if doc:
                    doc.status = "COMPLETED"

                tool_calls.append(
                    {
                        "tool": "post_invoice_erp",
                        "status": "SUCCESS",
                        "invoice_id": inv.id,
                        "duration_ms": t_tool_elapsed,
                    }
                )
                logs.append(f"Action: Successfully posted invoice {inv.invoice_number} to ERP system")
            else:
                # Escalate to Human Review Queue
                t_tool_start = time.time()
                review_out = await self.tools.create_review_task(
                    ctx,
                    CreateReviewTaskInput(
                        document_id=doc_id,
                        reason=state.get("decision_reason", "Validation exception"),
                        priority="HIGH" if "High-value" in state.get("decision_reason", "") else "MEDIUM",
                    ),
                )
                t_tool_elapsed = max(int((time.time() - t_tool_start) * 1000), 1)
                review_task_id = review_out["task_id"]

                # Update document status
                stmt = select(Document).where(Document.id == doc_id, Document.tenant_id == state["tenant_id"])
                doc = (await self.db.execute(stmt)).scalar_one_or_none()
                if doc:
                    doc.status = "REVIEW_REQUIRED"

                tool_calls.append(
                    {
                        "tool": "create_review_task",
                        "status": "SUCCESS",
                        "task_id": review_task_id,
                        "duration_ms": t_tool_elapsed,
                    }
                )
                logs.append(f"Action: Created Human Review Task {review_task_id}")

            out = {
                "review_task_id": review_task_id,
                "invoice_id": invoice_id,
                "logs": logs,
                "tool_calls_executed": tool_calls,
            }
            elapsed = int((time.time() - start_t) * 1000)
            if state.get("workflow_run_id"):
                await self._record_step(
                    state["workflow_run_id"], state["tenant_id"], "action", "SUCCESS", state, out, elapsed
                )
            return out

        # Register nodes in LangGraph
        workflow.add_node("intake", intake_node)
        workflow.add_node("classification", classification_node)
        workflow.add_node("extraction", extraction_node)
        workflow.add_node("validation", validation_node)
        workflow.add_node("rag_policy", rag_policy_node)
        workflow.add_node("decision", decision_node)
        workflow.add_node("action", action_node)

        # Connect edges
        workflow.set_entry_point("intake")
        workflow.add_edge("intake", "classification")
        workflow.add_edge("classification", "extraction")
        workflow.add_edge("extraction", "validation")
        workflow.add_edge("validation", "rag_policy")
        workflow.add_edge("rag_policy", "decision")
        workflow.add_edge("decision", "action")
        workflow.add_edge("action", END)

        return workflow.compile()

    async def execute_workflow(self, initial_state: OpsPilotState) -> OpsPilotState:
        """Executes the complete compiled LangGraph workflow end-to-end."""
        wf_start_t = time.time()
        app_graph = self.build_graph()
        final_state = await app_graph.ainvoke(initial_state)
        total_duration_ms = max(int((time.time() - wf_start_t) * 1000), 1)

        # Update Document and WorkflowRun records with results
        wf_id = final_state.get("workflow_run_id")
        doc_id = final_state.get("document_id")
        tenant_id = final_state.get("tenant_id")

        if wf_id:
            stmt = select(WorkflowRun).where(WorkflowRun.id == wf_id, WorkflowRun.tenant_id == tenant_id)
            wf = (await self.db.execute(stmt)).scalar_one_or_none()
            if wf:
                wf.status = "COMPLETED" if final_state.get("decision") == "APPROVE_AUTOMATICALLY" else "REVIEW_REQUIRED"
                wf.current_step = "action"
                wf.result_summary = final_state.get("decision_reason")

            # Record AgentRun telemetry
            agent_run = AgentRun(
                tenant_id=tenant_id,
                workflow_run_id=wf_id,
                model=final_state.get("model") or getattr(self.llm, "model", "mock-agent-v1"),
                provider=final_state.get("provider") or getattr(self.llm, "provider", "mock"),
                usage_source=final_state.get("usage_source", "estimated"),
                input_tokens=final_state.get("input_tokens", 0),
                output_tokens=final_state.get("output_tokens", 0),
                total_cost=final_state.get("total_cost", 0.0),
                duration_ms=total_duration_ms,
            )
            self.db.add(agent_run)
            await self.db.flush()

            # Record Tool Calls telemetry
            for tc in final_state.get("tool_calls_executed", []):
                call = ToolCall(
                    tenant_id=tenant_id,
                    agent_run_id=agent_run.id,
                    tool_name=tc.get("tool", "unknown"),
                    input_json=json.dumps({"document_id": doc_id}),
                    output_json=json.dumps(tc),
                    status=tc.get("status", "SUCCESS"),
                    duration_ms=tc.get("duration_ms", 10),
                )
                self.db.add(call)

        # Persist DocumentExtraction
        if doc_id and final_state.get("extracted_data"):
            ext_stmt = select(DocumentExtraction).where(
                DocumentExtraction.document_id == doc_id, DocumentExtraction.tenant_id == tenant_id
            )
            existing_ext = (await self.db.execute(ext_stmt)).scalar_one_or_none()
            ext_dict = final_state["extracted_data"]
            confs_dict = final_state.get("field_confidences", {})
            findings_list = final_state.get("validation_result", {}).get("findings", [])

            if not existing_ext:
                new_ext = DocumentExtraction(
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    schema_type="invoice",
                    raw_json=json.dumps(ext_dict),
                    structured_data=json.dumps(ext_dict),
                    field_confidences=json.dumps(confs_dict),
                    validation_findings=json.dumps(findings_list),
                    is_valid=final_state.get("validation_result", {}).get("is_clean", False),
                )
                self.db.add(new_ext)
            else:
                existing_ext.structured_data = json.dumps(ext_dict)
                existing_ext.field_confidences = json.dumps(confs_dict)
                existing_ext.validation_findings = json.dumps(findings_list)
                existing_ext.is_valid = final_state.get("validation_result", {}).get("is_clean", False)

        # Update Document classification & confidence
        if doc_id:
            doc_stmt = select(Document).where(Document.id == doc_id, Document.tenant_id == tenant_id)
            doc_rec = (await self.db.execute(doc_stmt)).scalar_one_or_none()
            if doc_rec:
                doc_rec.classification = final_state.get("classification")
                doc_rec.confidence_score = final_state.get("classification_confidence")

        await self.db.commit()
        return final_state
