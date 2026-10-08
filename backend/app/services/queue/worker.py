import asyncio
import time
from typing import Any, Dict, Optional
from sqlalchemy import select
from app.core.config import get_settings
from app.core.logging import logger
import app.db.session as session_module
from app.models.document import Document
from app.models.workflow import WorkflowRun
from app.services.agents.graph import AgentWorkflowService
from app.services.agents.state import OpsPilotState
from app.services.llm.factory import get_llm_provider
from app.services.storage import get_storage_provider

from app.services.queue.base import BaseQueueBackend
from app.services.queue.in_memory import InMemoryQueueBackend
from app.services.queue.redis import RedisQueueBackend

settings = get_settings()


class JobQueueWorker:
    """
    Durable asynchronous queue worker with bounded retries, exponential backoff,
    dead-letter escalation, and idempotent job execution across in-memory and Redis backends.
    """

    def __init__(self, backend: Optional[BaseQueueBackend] = None):
        if backend is not None:
            self.backend = backend
        elif settings.USE_IN_MEMORY_QUEUE or settings.WORKER_MODE == "in_process":
            self.backend = InMemoryQueueBackend()
        else:
            self.backend = RedisQueueBackend(redis_url=settings.REDIS_URL)
        self._is_running = False
        self._worker_task: Optional[asyncio.Task] = None

    async def enqueue_job(self, document_id: str, tenant_id: str, user_id: str, user_role: str) -> str:
        """Enqueues an asynchronous processing job returning the workflow run ID."""
        async with session_module.AsyncSessionLocal() as db:
            # Create persistent WorkflowRun in PENDING state
            wf = WorkflowRun(
                tenant_id=tenant_id,
                document_id=document_id,
                status="PENDING",
                current_step="queued",
            )
            db.add(wf)
            await db.commit()
            await db.refresh(wf)
            workflow_run_id = wf.id

        job = {
            "workflow_run_id": workflow_run_id,
            "document_id": document_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "user_role": user_role,
            "attempt": 1,
            "max_attempts": 3,
        }
        await self.backend.enqueue(job)
        logger.info(f"Enqueued document job: doc_id={document_id}, wf_id={workflow_run_id}")
        return workflow_run_id

    async def _process_single_job(self, job: Dict[str, Any]) -> None:
        doc_id = job["document_id"]
        tenant_id = job["tenant_id"]
        wf_id = job["workflow_run_id"]

        logger.info(f"Processing job {wf_id} for doc {doc_id} (Attempt {job['attempt']})")

        async with session_module.AsyncSessionLocal() as db:
            # Idempotency check: read current document state
            stmt = select(Document).where(Document.id == doc_id, Document.tenant_id == tenant_id)
            doc = (await db.execute(stmt)).scalar_one_or_none()
            if not doc:
                logger.error(f"Document {doc_id} not found in database; aborting job.")
                return

            # Update document to PROCESSING
            doc.status = "PROCESSING"
            wf_stmt = select(WorkflowRun).where(WorkflowRun.id == wf_id, WorkflowRun.tenant_id == tenant_id)
            wf = (await db.execute(wf_stmt)).scalar_one_or_none()
            if wf:
                wf.status = "RUNNING"
            await db.commit()

            # Read document file content using modular parser router
            storage = get_storage_provider()
            from app.models.document import DocumentPage
            from app.services.parsing.router import get_document_parser_router

            try:
                file_bytes = await storage.get_file(doc.storage_path)
                parser_router = get_document_parser_router()
                parsed_doc = await parser_router.parse_document(file_bytes, doc.filename)
                raw_text = parsed_doc.text

                # Persist page-level parsed text
                for p in parsed_doc.pages:
                    page_record = DocumentPage(
                        document_id=doc.id,
                        page_number=p.page_number,
                        text=p.text,
                        confidence_score=p.confidence,
                    )
                    db.add(page_record)
                await db.commit()
            except Exception as parse_err:
                logger.error(f"Document parsing failed for doc {doc_id}: {parse_err}")
                doc.status = "FAILED"
                if wf:
                    wf.status = "FAILED"
                    wf.failure_code = "PARSING_ERROR"
                    wf.failure_message = str(parse_err)
                    wf.result_summary = f"Document parsing failed: {str(parse_err)}"
                await db.commit()
                return

            # Construct initial LangGraph State
            initial_state: OpsPilotState = {
                "tenant_id": tenant_id,
                "user_id": job["user_id"],
                "user_role": job["user_role"],
                "document_id": doc_id,
                "workflow_run_id": wf_id,
                "filename": doc.filename,
                "file_type": doc.file_type,
                "raw_text": raw_text,
                "logs": [f"Worker started job {wf_id} at {time.strftime('%X')}"],
                "tool_calls_executed": [],
                "total_tokens": 0,
                "total_cost": 0.0,
            }

            llm = get_llm_provider()
            workflow_svc = AgentWorkflowService(db, llm)

            try:
                await workflow_svc.execute_workflow(initial_state)
                logger.info(f"Job {wf_id} completed successfully.")
            except Exception as exc:
                logger.error(f"Error processing job {wf_id}: {exc}", exc_info=True)
                if job["attempt"] < job["max_attempts"]:
                    job["attempt"] += 1
                    backoff_delay = 2 ** (job["attempt"] - 1)
                    logger.info(f"Retrying job {wf_id} in {backoff_delay}s...")
                    if wf:
                        wf.retry_count = job["attempt"]
                        await db.commit()
                    await asyncio.sleep(backoff_delay)
                    await self.backend.enqueue(job)
                else:
                    logger.error(f"Job {wf_id} exceeded max retries. Routing to Dead Letter Queue (DLQ).")
                    await self.backend.enqueue_dlq(job)
                    # Mark document as FAILED
                    doc.status = "FAILED"
                    if wf:
                        wf.status = "FAILED"
                        wf.retry_count = job["attempt"]
                        wf.failure_code = "PIPELINE_ERROR"
                        wf.failure_message = str(exc)
                        wf.result_summary = f"Processing failed after max retries: {str(exc)}"
                    await db.commit()

    async def _worker_loop(self):
        while self._is_running:
            try:
                job = await self.backend.dequeue(timeout=1.0)
                if job is None:
                    continue
                await self._process_single_job(job)
                if hasattr(self.backend, "task_done"):
                    self.backend.task_done()
            except Exception as e:
                logger.error(f"Unexpected worker loop exception: {e}", exc_info=True)

    def start(self):
        if not self._is_running:
            self._is_running = True
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("Asynchronous JobQueueWorker started.")

    async def stop(self):
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Asynchronous JobQueueWorker stopped.")

    async def get_queue_depth(self) -> int:
        return await self.backend.get_depth()

    async def get_dlq_depth(self) -> int:
        return await self.backend.get_dlq_depth()


_job_worker_instance = JobQueueWorker()


def get_job_worker() -> JobQueueWorker:
    return _job_worker_instance
