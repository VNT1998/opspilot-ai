import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.models.erp import Invoice, PurchaseOrder
from app.schemas.extraction import InvoiceExtractionSchema
from app.schemas.validation import BusinessValidationResult, ValidationFinding
from app.services.validation.policies import requires_high_value_approval, within_po_tolerance

settings = get_settings()


def to_decimal(val: Any) -> Decimal:
    """Normalize any numeric representation to 2-decimal-place Decimal."""
    if val is None:
        return Decimal("0.00")
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ValidationEngine:
    """
    Deterministic rule-based validation engine.
    Ensures mathematical consistency, PO invoice-to-PO matching, tolerance verification,
    and policy threshold checks without relying on LLM arithmetic.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_invoice(
        self,
        tenant_id: str,
        extraction: InvoiceExtractionSchema,
        field_confidences: Optional[Dict[str, float]] = None,
        raw_text: Optional[str] = None,
    ) -> BusinessValidationResult:
        field_confidences = field_confidences or {}
        findings: List[ValidationFinding] = []
        requires_review = False
        routing_reasons: List[str] = []

        # 0. Check for adversarial prompt injection patterns in raw text and fields
        text_to_scan = (raw_text or "") + " " + (extraction.vendor_name or "") + " " + (extraction.invoice_number or "")
        if extraction.line_items:
            for item in extraction.line_items:
                text_to_scan += " " + (item.description or "")

        injection_patterns = [
            r"ignore\s+(all\s+|previous\s+|prior\s+)?instructions",
            r"system\s+(override|instruction|prompt)",
            r"approve\s+(automatically|immediately|without\s+validation)",
            r"skip\s+(validation|check|verification)",
            r"bypass\s+(security|authorization|rules)",
            r"maintenance\s+debug\s+mode",
            r"debug\s+mode\s+enabled",
            r"developer\s+(mode|instruction)",
            r"role\s+escalation",
            r"unlimited\s+approval\s+authority",
        ]
        if any(re.search(p, text_to_scan, re.IGNORECASE) for p in injection_patterns):
            findings.append(
                ValidationFinding(
                    rule_name="prompt_injection_defense",
                    passed=False,
                    severity="ERROR",
                    message="Adversarial prompt injection pattern detected in document content. Blocked automated straight-through execution.",
                )
            )
            requires_review = True
            routing_reasons.append("Adversarial prompt injection pattern detected")

        # 1. Check Mandatory Fields
        if not extraction.invoice_number or extraction.invoice_number.strip() == "":
            findings.append(
                ValidationFinding(
                    rule_name="mandatory_invoice_number",
                    passed=False,
                    severity="ERROR",
                    message="Invoice number is missing",
                )
            )
            requires_review = True
            routing_reasons.append("Missing invoice number")
        else:
            findings.append(
                ValidationFinding(
                    rule_name="mandatory_invoice_number",
                    passed=True,
                    severity="INFO",
                    message="Invoice number present",
                    actual_value=extraction.invoice_number,
                )
            )

        # 2. Check Mathematical Integrity: Subtotal + Tax == Total
        subtotal_dec = to_decimal(extraction.subtotal)
        tax_dec = to_decimal(extraction.tax)
        total_dec = to_decimal(extraction.total)
        expected_total_dec = subtotal_dec + tax_dec
        total_diff_dec = abs(expected_total_dec - total_dec)
        if total_diff_dec > Decimal("0.05"):
            findings.append(
                ValidationFinding(
                    rule_name="tax_subtotal_arithmetic",
                    passed=False,
                    severity="ERROR",
                    message=f"Subtotal ({subtotal_dec}) + Tax ({tax_dec}) != Total ({total_dec})",
                    expected_value=float(expected_total_dec),
                    actual_value=float(total_dec),
                )
            )
            requires_review = True
            routing_reasons.append("Subtotal/Tax arithmetic mismatch")
        else:
            findings.append(
                ValidationFinding(
                    rule_name="tax_subtotal_arithmetic",
                    passed=True,
                    severity="INFO",
                    message="Subtotal + Tax matches Total",
                )
            )

        # 3. Check Line Items Sum vs Subtotal
        if extraction.line_items:
            line_sum_dec = sum(
                (to_decimal(item.quantity) * to_decimal(item.unit_price)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                for item in extraction.line_items
            )
            line_diff_dec = abs(line_sum_dec - subtotal_dec)
            if line_diff_dec > Decimal("0.10"):
                findings.append(
                    ValidationFinding(
                        rule_name="line_items_reconciliation",
                        passed=False,
                        severity="WARNING",
                        message=f"Sum of line items ({line_sum_dec}) differs from subtotal ({subtotal_dec})",
                        expected_value=float(subtotal_dec),
                        actual_value=float(line_sum_dec),
                    )
                )
                requires_review = True
                routing_reasons.append("Line items sum discrepancy")
            else:
                findings.append(
                    ValidationFinding(
                        rule_name="line_items_reconciliation",
                        passed=True,
                        severity="INFO",
                        message="Line items reconcile with subtotal",
                    )
                )

        # 4. Check Purchase Order matching & Variance
        variance_amount_dec = Decimal("0.00")
        variance_percent_dec = Decimal("0.00")
        if extraction.po_number:
            stmt = select(PurchaseOrder).where(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.po_number == extraction.po_number,
            )
            res = await self.db.execute(stmt)
            po = res.scalar_one_or_none()

            if not po:
                findings.append(
                    ValidationFinding(
                        rule_name="po_existence_check",
                        passed=False,
                        severity="WARNING",
                        message=f"Referenced Purchase Order '{extraction.po_number}' not found in ERP system",
                        actual_value=extraction.po_number,
                    )
                )
                requires_review = True
                routing_reasons.append(f"Referenced PO '{extraction.po_number}' not found")
            else:
                # PO exists, calculate variance with Decimal precision
                po_total_dec = to_decimal(po.total_amount)
                variance_amount_dec = abs(total_dec - po_total_dec)
                variance_percent_dec = (
                    ((variance_amount_dec / po_total_dec) * Decimal("100.00")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    if po_total_dec > Decimal("0.00")
                    else Decimal("0.00")
                )

                if within_po_tolerance(variance_percent_dec, variance_amount_dec):
                    findings.append(
                        ValidationFinding(
                            rule_name="po_tolerance_check",
                            passed=True,
                            severity="INFO",
                            message=f"PO variance within tolerance: ${variance_amount_dec} ({variance_percent_dec}%)",
                            expected_value=float(po_total_dec),
                            actual_value=float(total_dec),
                        )
                    )
                else:
                    findings.append(
                        ValidationFinding(
                            rule_name="po_tolerance_check",
                            passed=False,
                            severity="ERROR",
                            message=f"PO variance exceeds tolerance: ${variance_amount_dec} ({variance_percent_dec}% > {settings.VARIANCE_TOLERANCE_PERCENT}%)",
                            expected_value=float(po_total_dec),
                            actual_value=float(total_dec),
                        )
                    )
                    requires_review = True
                    routing_reasons.append(f"PO variance {variance_percent_dec}% exceeds tolerance threshold")
        else:
            findings.append(
                ValidationFinding(
                    rule_name="po_reference",
                    passed=False,
                    severity="INFO",
                    message="No Purchase Order referenced in invoice",
                )
            )

        # 5. Check High-Value Policy Threshold (>= $10,000)
        high_value_dec = to_decimal(settings.HIGH_VALUE_THRESHOLD)
        if requires_high_value_approval(total_dec):
            findings.append(
                ValidationFinding(
                    rule_name="high_value_policy_threshold",
                    passed=False,
                    severity="WARNING",
                    message=f"Invoice total (${total_dec}) meets or exceeds high-value policy threshold (${high_value_dec})",
                    expected_value=float(high_value_dec),
                    actual_value=float(total_dec),
                )
            )
            requires_review = True
            routing_reasons.append("High-value policy threshold ($10,000) requires human sign-off")

        # 6. Check Duplicate Invoice in DB
        dup_stmt = select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.invoice_number == extraction.invoice_number,
        )
        dup_res = await self.db.execute(dup_stmt)
        if dup_res.first():
            findings.append(
                ValidationFinding(
                    rule_name="duplicate_invoice_prevention",
                    passed=False,
                    severity="ERROR",
                    message=f"Duplicate invoice detected: '{extraction.invoice_number}' already exists in ERP",
                    actual_value=extraction.invoice_number,
                )
            )
            requires_review = True
            routing_reasons.append(f"Duplicate invoice '{extraction.invoice_number}' detected")

        # 7. Check Confidence Score Threshold
        conf_values = list(field_confidences.values())
        avg_confidence = round(sum(conf_values) / len(conf_values), 3) if conf_values else 0.0

        if avg_confidence < settings.AUTO_APPROVE_CONFIDENCE_THRESHOLD:
            findings.append(
                ValidationFinding(
                    rule_name="confidence_threshold_check",
                    passed=False,
                    severity="WARNING",
                    message=f"Average extraction confidence ({avg_confidence}) below automated approval threshold ({settings.AUTO_APPROVE_CONFIDENCE_THRESHOLD})",
                    expected_value=settings.AUTO_APPROVE_CONFIDENCE_THRESHOLD,
                    actual_value=avg_confidence,
                )
            )
            requires_review = True
            routing_reasons.append(f"Low AI confidence ({avg_confidence})")
        else:
            findings.append(
                ValidationFinding(
                    rule_name="confidence_threshold_check",
                    passed=True,
                    severity="INFO",
                    message=f"Extraction confidence ({avg_confidence}) satisfies automated processing criteria",
                    expected_value=settings.AUTO_APPROVE_CONFIDENCE_THRESHOLD,
                    actual_value=avg_confidence,
                )
            )

        is_clean = len([f for f in findings if not f.passed and f.severity == "ERROR"]) == 0 and not requires_review

        return BusinessValidationResult(
            is_clean=is_clean,
            confidence_score=avg_confidence,
            variance_amount=float(variance_amount_dec),
            variance_percent=float(variance_percent_dec),
            requires_human_review=requires_review,
            routing_reason="; ".join(routing_reasons) if routing_reasons else None,
            findings=findings,
        )
