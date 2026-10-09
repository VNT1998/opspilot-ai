from decimal import Decimal
from typing import Dict, Optional, Set
from app.core.config import get_settings

_settings = get_settings()
# Canonical business policy constants bound to config
PO_TOLERANCE_PERCENT = Decimal(str(_settings.VARIANCE_TOLERANCE_PERCENT))
PO_TOLERANCE_AMOUNT = Decimal(str(_settings.VARIANCE_TOLERANCE_ABSOLUTE))
HIGH_VALUE_THRESHOLD = Decimal(str(_settings.HIGH_VALUE_THRESHOLD))

# Allowed Review Task state transitions
ALLOWED_REVIEW_TRANSITIONS: Dict[str, Set[str]] = {
    "PENDING": {"RESOLVED", "REJECTED", "PENDING"},
    "RESOLVED": set(),  # Terminal state
    "REJECTED": set(),  # Terminal state
}


def within_po_tolerance(variance_percent: Decimal, variance_amount: Decimal) -> bool:
    """
    Evaluates whether invoice variance is within acceptable matching tolerance.
    Tolerance: variance percentage <= 2.00% AND variance absolute amount <= $5.00.
    """
    return variance_percent <= PO_TOLERANCE_PERCENT and variance_amount <= PO_TOLERANCE_AMOUNT


def requires_high_value_approval(total: Decimal) -> bool:
    """
    Returns True if invoice total is at or above the high-value approval threshold ($10,000.00).
    Invoices requiring high-value approval require ops_manager or admin role.
    """
    return total >= HIGH_VALUE_THRESHOLD


def allowed_review_transition(current_status: str, requested_status: str) -> bool:
    """
    Enforces deterministic state machine transitions for human-in-the-loop review tasks.
    Terminal states cannot transition to any other state.
    """
    curr = current_status.upper()
    req = requested_status.upper()
    allowed = ALLOWED_REVIEW_TRANSITIONS.get(curr, set())
    return req in allowed


def is_auto_approvable(
    is_valid: bool,
    confidence_score: float,
    total_amount: Optional[Decimal] = None,
    min_confidence: float = 0.85,
) -> bool:
    """
    Determines if a document/invoice can be auto-approved without human review.
    Must be valid, meet minimum extraction confidence, and not exceed high-value threshold.
    """
    if not is_valid:
        return False
    if confidence_score < min_confidence:
        return False
    if total_amount is not None and requires_high_value_approval(total_amount):
        return False
    return True
