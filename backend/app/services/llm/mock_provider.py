import hashlib
import re
from typing import Dict, List, Tuple, Type, TypeVar
import numpy as np
from pydantic import BaseModel
from app.schemas.extraction import InvoiceExtractionSchema, InvoiceLineSchema

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider:
    """
    Deterministic Mock LLM Provider for local development, CI/CD, and offline testing ONLY.
    STRICTLY PROHIBITED IN PRODUCTION ENVIRONMENTS.
    Provides schema-validated extractions, realistic field confidences, normalized vector embeddings,
    and prompt-injection safety defenses for regression testing.
    """

    usage_source: str = "estimated"
    provider: str = "mock"
    model: str = "mock-agent-v1"

    async def generate(self, prompt: str, system: str = "") -> str:
        # Check for prompt injection attempts in prompt
        lower_prompt = prompt.lower()
        if "ignore previous instructions" in lower_prompt or "ignore all instructions" in lower_prompt:
            return "Security Alert: Detected untrusted instruction attempting system override. Request declined."

        if "summarize" in lower_prompt:
            return "OpsPilot AI processed this document according to enterprise business policy. All mandatory fields have been reconciled."
        return "OpsPilot Agent completed execution with verified findings."

    async def classify_document(self, text: str, filename: str) -> Tuple[str, float]:
        combined = f"{filename} {text}".lower()
        if "invoice" in combined or "inv-" in combined or "bill to" in combined or "amount due" in combined:
            return ("invoice", 0.96)
        if "purchase order" in combined or "po-" in combined or "order confirmation" in combined:
            return ("purchase_order", 0.94)
        if "agreement" in combined or "contract" in combined or "terms and conditions" in combined:
            return ("contract", 0.92)
        if "receipt" in combined or "payment receipt" in combined:
            return ("receipt", 0.91)
        return ("other", 0.70)

    async def extract_structured(self, text: str, schema: Type[T]) -> Tuple[T, Dict[str, float]]:
        """Extracts structured invoice or PO data with realistic field confidence scores."""
        # Check if text is poor quality or handwriting
        is_poor_quality = any(
            k in text.lower() for k in ["poor scan", "handwritten", "blurry", "low_quality", "smudge"]
        )

        # Invoice number pattern
        inv_match = re.search(r"(?:invoice\s*(?:#|no|number)\s*[:\s]+)([A-Z0-9\-]+)", text, re.IGNORECASE)
        if not inv_match:
            inv_match = re.search(r"\b(INV-[A-Z0-9\-]+)\b", text, re.IGNORECASE)
        inv_num = inv_match.group(1).strip() if inv_match else "INV-2026-001"

        po_match = re.search(r"(?:po\s*(?:#|no|number)\s*[:\s]+)([A-Z0-9\-]+)", text, re.IGNORECASE)
        if not po_match:
            po_match = re.search(r"\b(PO-[A-Z0-9\-]+)\b", text, re.IGNORECASE)
        po_num = po_match.group(1).strip() if po_match else "PO-9001"

        vendor_match = re.search(r"(?:vendor|supplier|from)[:\s]+([A-Za-z0-9\s,\.]+?)(?:\n|$)", text, re.IGNORECASE)
        vendor_name = vendor_match.group(1).strip() if vendor_match else "Acme Industrial Supplies"

        # Check total amount (avoid matching 'subtotal')
        total_match = re.search(
            r"\b(?:total(?:\s+amount)?(?:\s+due)?|amount due|balance)\b[:\s]*\$?([0-9,]+\.?[0-9]*)", text, re.IGNORECASE
        )
        if total_match:
            try:
                total_val = float(total_match.group(1).replace(",", ""))
            except ValueError:
                total_val = 1450.00
        else:
            total_val = 1450.00

        # Subtotal match
        subtotal_match = re.search(r"(?:subtotal)[:\s]*\$?([0-9,]+\.?[0-9]*)", text, re.IGNORECASE)
        if subtotal_match:
            try:
                subtotal_val = float(subtotal_match.group(1).replace(",", ""))
            except ValueError:
                subtotal_val = round(total_val / 1.10, 2)
        else:
            subtotal_val = round(total_val / 1.10, 2)

        # Tax match
        tax_match = re.search(r"(?:tax)[:\s]*\$?([0-9,]+\.?[0-9]*)", text, re.IGNORECASE)
        if tax_match:
            try:
                tax_val = float(tax_match.group(1).replace(",", ""))
            except ValueError:
                tax_val = round(total_val - subtotal_val, 2)
        else:
            tax_val = round(total_val - subtotal_val, 2)

        # Baseline confidences
        base_conf = 0.62 if is_poor_quality else 0.96

        line_items = [
            InvoiceLineSchema(
                description="Standard Enterprise Service License",
                quantity=1.0,
                unit_price=subtotal_val,
                tax=tax_val,
                total_price=total_val,
                sku="SRV-100",
            )
        ]

        data = InvoiceExtractionSchema(
            invoice_number=inv_num,
            invoice_date="2026-10-01",
            vendor_name=vendor_name,
            currency="USD",
            subtotal=subtotal_val,
            tax=tax_val,
            total=total_val,
            payment_terms="Net 30",
            po_number=po_num,
            line_items=line_items,
        )

        confidences = {
            "invoice_number": round(base_conf - 0.01, 2),
            "invoice_date": round(base_conf, 2),
            "vendor_name": round(base_conf - 0.02, 2),
            "subtotal": round(base_conf, 2),
            "tax": round(base_conf - 0.03, 2),
            "total": round(base_conf, 2),
            "po_number": round(base_conf - 0.04, 2),
            "line_items": round(base_conf - 0.05, 2),
        }

        return (data, confidences)

    async def embed(self, text: str) -> List[float]:
        """
        Produces a normalized 128-dimensional dense vector representation.
        Deterministic and semantically meaningful using word-hash projection.
        """
        dim = 128
        vec = np.zeros(dim, dtype=np.float32)
        words = re.findall(r"\w+", text.lower())
        if not words:
            vec[0] = 1.0
            return vec.tolist()

        for word in words:
            # Deterministic hash to dimension index
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vec[idx] += sign

        # L2 normalization
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return [float(x) for x in vec]
