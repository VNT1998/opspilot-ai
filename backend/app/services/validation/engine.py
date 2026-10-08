from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.models.erp import Invoice, PurchaseOrder, Vendor
from app.schemas.extraction import InvoiceExtractionSchema
from app.schemas.validation import BusinessValidationResult, ValidationFinding

settings = get_settings()


class ValidationEngine:
    """
    Deterministic rule-based validation engine.
    Ensures mathematical consistency, PO 3-way matching, tolerance verification,
    and policy threshold checks without relying on LLM arithmetic.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_invoice(
        self,
        tenant_id: str,
        extraction: InvoiceExtractionSchema,
        field_confidences: Dict[str, float],
    ) -> BusinessValidationResult:
        findings: List[ValidationFinding] = []
        requires_review = False
        routing_reasons: List[str] = []

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
        expected_total = round(extraction.subtotal + extraction.tax, 2)
        actual_total = round(extraction.total, 2)
        total_diff = round(abs(expected_total - actual_total), 2)
        if total_diff > 0.05:
            findings.append(
                ValidationFinding(
                    rule_name="tax_subtotal_arithmetic",
                    passed=False,
                    severity="ERROR",
                    message=f"Subtotal ({extraction.subtotal}) + Tax ({extraction.tax}) != Total ({extraction.total})",
                    expected_value=expected_total,
                    actual_value=actual_total,
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
            line_sum = sum(round(item.quantity * item.unit_price, 2) for item in extraction.line_items)
            line_diff = round(abs(line_sum - extraction.subtotal), 2)
            if line_diff > 0.10:
                findings.append(
                    ValidationFinding(
                        rule_name="line_items_reconciliation",
                        passed=False,
                        severity="WARNING",
                        message=f"Sum of line items ({line_sum}) differs from subtotal ({extraction.subtotal})",
                        expected_value=extraction.subtotal,
                        actual_value=line_sum,
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
        variance_amount = 0.0
        variance_percent = 0.0
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
                # PO exists, calculate variance
                variance_amount = round(abs(extraction.total - po.total_amount), 2)
                variance_percent = round((variance_amount / po.total_amount) * 100.0, 2) if po.total_amount > 0 else 0.0

                within_percent = variance_percent <= settings.VARIANCE_TOLERANCE_PERCENT
                within_abs = variance_amount <= settings.VARIANCE_TOLERANCE_ABSOLUTE

                if within_percent or within_abs:
                    findings.append(
                        ValidationFinding(
                            rule_name="po_tolerance_check",
                            passed=True,
                            severity="INFO",
                            message=f"PO variance within tolerance: ${variance_amount} ({variance_percent}%)",
                            expected_value=po.total_amount,
                            actual_value=extraction.total,
                        )
                    )
                else:
                    findings.append(
                        ValidationFinding(
                            rule_name="po_tolerance_check",
                            passed=False,
                            severity="ERROR",
                            message=f"PO variance exceeds tolerance: ${variance_amount} ({variance_percent}% > {settings.VARIANCE_TOLERANCE_PERCENT}%)",
                            expected_value=po.total_amount,
                            actual_value=extraction.total,
                        )
                    )
                    requires_review = True
                    routing_reasons.append(f"PO variance {variance_percent}% exceeds tolerance threshold")
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
        if extraction.total >= settings.HIGH_VALUE_THRESHOLD:
            findings.append(
                ValidationFinding(
                    rule_name="high_value_policy_threshold",
                    passed=False,
                    severity="WARNING",
                    message=f"Invoice total (${extraction.total}) meets or exceeds high-value policy threshold (${settings.HIGH_VALUE_THRESHOLD})",
                    expected_value=settings.HIGH_VALUE_THRESHOLD,
                    actual_value=extraction.total,
                )
            )
            requires_review = True
            routing_reasons.append(f"High-value policy threshold ($10,000) requires human sign-off")

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
            variance_amount=variance_amount,
            variance_percent=variance_percent,
            requires_human_review=requires_review,
            routing_reason="; ".join(routing_reasons) if routing_reasons else None,
            findings=findings,
        )
