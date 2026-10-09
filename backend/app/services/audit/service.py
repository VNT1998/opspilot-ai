import hashlib
import json
from typing import Any, Dict, Optional
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLog

REDACTED_KEYS = {"password", "secret", "token", "api_key", "authorization", "hashed_password"}


def _sanitize_dict(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not d:
        return None
    cleaned = {}
    for k, v in d.items():
        if any(secret_term in k.lower() for secret_term in REDACTED_KEYS):
            cleaned[k] = "[REDACTED]"
        elif isinstance(v, dict):
            cleaned[k] = _sanitize_dict(v)
        else:
            cleaned[k] = v
    return cleaned


class AuditService:
    @staticmethod
    def compute_canonical_hash(
        tenant_id: str,
        user_id: Optional[str],
        actor_type: str,
        action: str,
        entity_type: str,
        entity_id: str,
        reason: Optional[str],
        request_id: Optional[str],
        workflow_run_id: Optional[str],
        before_str: Optional[str],
        after_str: Optional[str],
        previous_event_hash: Optional[str],
    ) -> str:
        """Computes deterministic SHA-256 hash covering all security-relevant audit fields."""
        canonical_payload = (
            f"{tenant_id}:{user_id or ''}:{actor_type}:{action}:{entity_type}:{entity_id}:"
            f"{reason or ''}:{request_id or ''}:{workflow_run_id or ''}:"
            f"{before_str or ''}:{after_str or ''}:{previous_event_hash or 'GENESIS'}"
        )
        return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

    @staticmethod
    async def log_event(
        db: AsyncSession,
        tenant_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        user_id: Optional[str] = None,
        actor_type: str = "user",
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        commit: bool = False,
    ) -> AuditLog:
        """
        Records an append-oriented, tamper-evident audit event with SHA-256 hash chaining
        and sanitized payloads. By default commit=False so route or workflow owns atomic transaction boundary.
        """
        sanitized_before = _sanitize_dict(before_state)
        sanitized_after = _sanitize_dict(after_state)

        before_str = json.dumps(sanitized_before, sort_keys=True, default=str) if sanitized_before else None
        after_str = json.dumps(sanitized_after, sort_keys=True, default=str) if sanitized_after else None

        # Fetch previous event hash for this tenant for hash chaining
        prev_stmt = (
            select(AuditLog.event_hash)
            .where(AuditLog.tenant_id == tenant_id)
            .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
            .limit(1)
        )
        prev_res = await db.execute(prev_stmt)
        previous_event_hash = prev_res.scalar_one_or_none()

        event_hash = AuditService.compute_canonical_hash(
            tenant_id=tenant_id,
            user_id=user_id,
            actor_type=actor_type,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            request_id=request_id,
            workflow_run_id=workflow_run_id,
            before_str=before_str,
            after_str=after_str,
            previous_event_hash=previous_event_hash,
        )

        log = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            actor_type=actor_type,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            before_state=before_str,
            after_state=after_str,
            request_id=request_id,
            workflow_run_id=workflow_run_id,
            ip_address=ip_address,
            previous_event_hash=previous_event_hash,
            event_hash=event_hash,
        )
        db.add(log)
        if commit:
            await db.commit()
            await db.refresh(log)
        else:
            await db.flush()
        return log

    @staticmethod
    async def verify_chain(db: AsyncSession, tenant_id: str) -> bool:
        """
        Verifies the append-oriented cryptographic audit hash chain for a given tenant.
        Returns True if all event hashes and previous-hash links are valid and unaltered.
        """
        stmt = (
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id)
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
        logs = (await db.execute(stmt)).scalars().all()
        expected_prev_hash: Optional[str] = None

        for log in logs:
            if log.previous_event_hash != expected_prev_hash:
                return False

            calculated_hash = AuditService.compute_canonical_hash(
                tenant_id=log.tenant_id,
                user_id=log.user_id,
                actor_type=log.actor_type,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                reason=log.reason,
                request_id=log.request_id,
                workflow_run_id=log.workflow_run_id,
                before_str=log.before_state,
                after_str=log.after_state,
                previous_event_hash=expected_prev_hash,
            )
            if log.event_hash != calculated_hash:
                return False

            expected_prev_hash = log.event_hash

        return True
