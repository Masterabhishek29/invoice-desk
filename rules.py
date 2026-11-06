"""Deterministic policy. All money uses Decimal; limits never get tolerance."""
import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from models import Invoice

RULE_VERSION = "ap-policy-v2-po-lines"
TOLERANCE = Decimal("0.02")
ROOT = Path(__file__).parent


def normalize(text):
    # Preserve punctuation in invoice IDs to avoid silently merging distinct IDs.
    return " ".join((text or "").casefold().split())


def records(name):
    with (ROOT / "data" / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate(invoice: Invoice, prior: list[dict]):
    checks = []

    def check(code, status, reason, **values):
        checks.append(dict(code=code, status=status, reason=reason, values={k: str(v) for k, v in values.items()}))

    required = ["vendor_name", "invoice_number", "invoice_date", "po_reference", "currency", "subtotal", "tax", "total"]
    missing = [name for name in required if not getattr(invoice, name)]
    check("required", "review" if missing else "pass", "Missing fields require human review" if missing else "All header fields present", missing=", ".join(missing))
    evidence_missing = [name for name in required if not invoice.evidence.get(name, "").strip()]
    uncertain = invoice.quality != "clear" or bool(invoice.uncertainties) or bool(evidence_missing)
    check("reliability", "review" if uncertain else "pass", "Review document quality and evidence" if uncertain else "Extractor reports clear text with evidence; this is not a correctness guarantee", quality=invoice.quality, uncertainties=invoice.uncertainties, evidence_missing=evidence_missing)
    check("supported_currency", "pass" if invoice.currency == "USD" else "review", "This policy supports USD only", currency=invoice.currency)

    vendors = [v for v in records("vendors.csv") if normalize(v["vendor_name"]) == normalize(invoice.vendor_name)]
    vendor = vendors[0] if len(vendors) == 1 else None
    check("vendor", "review" if not vendor else ("pass" if vendor["approved"] == "true" else "reject"), "Vendor exact normalized name verification", extracted=invoice.vendor_name, matched=vendor["vendor_id"] if vendor else "No unique match")
    pos = [p for p in records("purchase_orders.csv") if normalize(p["po_reference"]) == normalize(invoice.po_reference)]
    po = pos[0] if len(pos) == 1 else None
    check("po_match", "pass" if po else "review", "Exact PO reference required; no fuzzy automatic matching", extracted=invoice.po_reference)
    if po:
        po_lines = [row for row in records("purchase_order_lines.csv") if normalize(row["po_reference"]) == normalize(po["po_reference"])]
        check("po_lines", "pass" if po_lines else "review", "PO header has separately identified line records", po_reference=po["po_reference"], line_count=len(po_lines))
        allocations = {}
        for item in invoice.line_items:
            matches = [row for row in po_lines if normalize(row["description"]) == normalize(item.description)]
            if len(matches) != 1:
                check("line_match", "review", "Invoice description needs a unique PO line match; ambiguous or different wording requires review", description=item.description, candidate_line_ids=[r["line_id"] for r in matches])
            else:
                row = matches[0]
                check("line_match", "pass", "Invoice description matched to PO line", description=item.description, po_line_id=row["line_id"])
                allocations.setdefault(row["line_id"], []).append(item.amount)
        for row in po_lines:
            values = allocations.get(row["line_id"], [])
            if not values or any(v is None for v in values):
                continue
            try:
                current = sum((Decimal(v) for v in values), Decimal("0"))
                consumed = sum((Decimal(item["amount"]) for run in prior if run["decision"] == "approved" and normalize(run["invoice"].get("po_reference")) == normalize(po["po_reference"]) for item in run["invoice"].get("line_items", []) if normalize(item.get("description")) == normalize(row["description"]) and item.get("amount") is not None), Decimal("0"))
                remaining = Decimal(row["net_limit"]) - Decimal(row["previously_invoiced"]) - consumed
                check("po_line_balance", "reject" if current > remaining else "pass", "Net invoice line amount must fit its PO line balance; no tolerance", line_id=row["line_id"], remaining_before=remaining, invoice_net=current, approved_net=consumed)
            except InvalidOperation:
                check("po_line_format", "review", "Invalid numeric value in line allocation")
        check("po_status", "pass" if po["status"] == "open" else "reject", "PO must be open", po_status=po["status"])
        if vendor:
            check("po_vendor", "pass" if po["vendor_id"] == vendor["vendor_id"] else "reject", "Invoice vendor must own the PO", po_vendor=po["vendor_id"], invoice_vendor=vendor["vendor_id"])
        check("currency", "pass" if invoice.currency == po["currency"] else "review", "Currency must match; no FX conversion", invoice=invoice.currency, po=po["currency"])

    duplicate = [r for r in prior if r.get("invoice") and normalize(r["invoice"].get("vendor_name")) == normalize(invoice.vendor_name) and normalize(r["invoice"].get("invoice_number")) == normalize(invoice.invoice_number) and invoice.invoice_number]
    check("duplicate_identity", "reject" if duplicate else "pass", "Vendor + invoice number checked across all previous extracted runs", prior_run=duplicate[0]["id"] if duplicate else "none")

    def decimal(value):
        if value is None:
            return None
        result = Decimal(value)
        if not result.is_finite() or result < 0:
            raise ValueError("Invalid non-negative decimal")
        return result

    try:
        subtotal, tax, total = [decimal(getattr(invoice, k)) for k in ("subtotal", "tax", "total")]
        if all(v is not None for v in (subtotal, tax, total)):
            delta = abs(subtotal + tax - total)
            check("total_arithmetic", "pass" if delta <= TOLERANCE else "review", "Subtotal + tax versus printed total; absolute USD 0.02 inclusive tolerance", subtotal=subtotal, tax=tax, total=total, difference=delta, tolerance=TOLERANCE)
        amounts = []
        complete = bool(invoice.line_items)
        for n, item in enumerate(invoice.line_items, 1):
            qty, price, amount = [decimal(v) for v in (item.quantity, item.unit_price, item.amount)]
            if any(v is None for v in (qty, price, amount)) or not item.description or not item.evidence:
                complete = False
            if amount is not None:
                amounts.append(amount)
            if all(v is not None for v in (qty, price, amount)):
                delta = abs(qty * price - amount)
                check(f"line_{n}", "pass" if delta <= TOLERANCE else "review", "Quantity × unit price versus printed line amount", quantity=qty, unit_price=price, amount=amount, difference=delta)
        check("line_completeness", "pass" if complete else "review", "Item descriptions, quantities, unit prices, amounts and evidence required")
        if subtotal is not None and len(amounts) == len(invoice.line_items) and amounts:
            delta = abs(sum(amounts, Decimal("0")) - subtotal)
            check("line_sum", "pass" if delta <= TOLERANCE else "review", "Line amounts versus subtotal", sum=sum(amounts, Decimal("0")), subtotal=subtotal, difference=delta)
        if po and total is not None:
            # Reservations include only approved runs; rejected/review runs do not consume.
            reserved = sum((Decimal(r["invoice"]["total"]) for r in prior if r["decision"] == "approved" and normalize(r["invoice"]["po_reference"]) == normalize(po["po_reference"])), Decimal("0"))
            limit, opening = Decimal(po["limit"]), Decimal(po["previously_invoiced"])
            remaining = limit - opening - reserved
            check("individual_limit", "reject" if total > limit else "pass", "Single invoice cannot exceed full PO limit; zero tolerance", total=total, limit=limit)
            check("cumulative_limit", "reject" if total > remaining else "pass", "Previously invoiced + approved reservations + current invoice must fit PO; zero tolerance", opening=opening, approved_reservations=reserved, remaining_before=remaining, current=total, remaining_after=remaining-total)
    except (InvalidOperation, ValueError):
        check("numeric_format", "review", "Invalid line-item numeric format; human verification required")

    # Unreliable extraction cannot justify a hard rejection based on guessed values.
    statuses = {c["status"] for c in checks}
    decision = "needs-review" if uncertain or missing else ("rejected" if "reject" in statuses else "needs-review" if "review" in statuses else "approved")
    return decision, checks
