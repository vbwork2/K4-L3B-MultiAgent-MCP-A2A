"""Payment and refund investigation owned by Person 3."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from ..agent_contracts import AgentResult, AgentTask
from ..agent_utils import ZERO, consume, in_window, money, number, scoped_order
from ..case_evidence import CaseEvidenceGateway
from ..trace import TraceWriter


def _events_in_scope(
    raw_events: Any, purchase_at: Any, next_purchase_at: Any
) -> list[dict[str, Any]]:
    if not isinstance(raw_events, list):
        return []
    return [
        dict(event)
        for event in raw_events
        if isinstance(event, Mapping)
        and (not purchase_at or in_window(event.get("event_at"), purchase_at, next_purchase_at))
    ]


async def investigate(
    task: AgentTask, gateway: CaseEvidenceGateway, trace: TraceWriter
) -> AgentResult:
    """Reconcile payment captures and refunds for verified orders."""

    order_id, snapshot, next_purchase = scoped_order(task)
    if not order_id:
        return AgentResult(
            case_id=task.case_id,
            actor="payment-refund",
            status="blocked",
            findings={
                "payment_analysis": {
                    "verdict": "insufficient_evidence",
                    "captured_total_brl": None,
                    "refunded_total_brl": None,
                    "refundable_total_brl": None,
                },
                "affected_entities": {"payment_references": []},
                "split_payment": False,
                "conflicts": [],
            },
            unresolved=("No order was resolved for payment investigation",),
        )

    refs: list[str] = []
    unresolved: list[str] = []
    purchase_at = snapshot.get("order_purchase_timestamp")
    payment_data: Mapping[str, Any] = {}
    refund_data: Mapping[str, Any] = {}
    try:
        payment = await consume(task, gateway, trace, "get_payment_timeline", order_id=order_id)
        refs.append(payment["evidence_ref"])
        if isinstance(payment.get("data"), Mapping):
            payment_data = payment["data"]
    except RuntimeError:
        unresolved.append("Payment timeline was unavailable from MCP")

    primary_topic = task.questions[0] if task.questions else ""
    if primary_topic in {"refund_pending", "refund_failed"}:
        try:
            refund = await consume(task, gateway, trace, "get_refund_timeline", order_id=order_id)
            refs.append(refund["evidence_ref"])
            if isinstance(refund.get("data"), Mapping):
                refund_data = refund["data"]
        except RuntimeError:
            unresolved.append("Refund timeline was unavailable from MCP")

    events = _events_in_scope(payment_data.get("events"), purchase_at, next_purchase)
    refund_events = _events_in_scope(refund_data.get("events"), purchase_at, next_purchase)
    captures = [
        event
        for event in events
        if event.get("event_type") == "captured" and event.get("status") == "confirmed"
    ]
    capture_amounts = [money(event.get("amount_brl")) for event in captures]
    captured: Decimal | None = (
        sum(capture_amounts, ZERO)
        if capture_amounts and all(amount is not None for amount in capture_amounts)
        else None
    )
    completed_refunds = [
        event
        for event in refund_events
        if event.get("status") in {"confirmed", "completed", "succeeded", "refunded"}
    ]
    refund_amounts = [money(event.get("amount_brl")) for event in completed_refunds]
    refunded: Decimal | None = (
        sum(refund_amounts, ZERO) if all(amount is not None for amount in refund_amounts) else None
    )
    refundable = (
        max(captured - refunded, ZERO) if captured is not None and refunded is not None else None
    )
    expected = None
    fulfillment = task.scope.get("fulfillment")
    if isinstance(fulfillment, AgentResult):
        expected = money(fulfillment.findings.get("expected_total_brl"))

    has_pending = any(event.get("status") == "pending" for event in refund_events)
    has_failed = any(event.get("status") == "failed" for event in refund_events)
    has_mismatch = any(event.get("event_type") == "reconciliation_mismatch" for event in events)
    base_payments = payment_data.get("payments", [])
    payment_rows = base_payments if isinstance(base_payments, list) else []
    capture_values = [str(amount) for amount in capture_amounts if amount is not None]
    matched_rows: list[Mapping[str, Any]] = []
    remaining = capture_values.copy()
    for row in payment_rows:
        if not isinstance(row, Mapping):
            continue
        amount = money(row.get("payment_value"))
        if amount is not None and str(amount) in remaining:
            matched_rows.append(row)
            remaining.remove(str(amount))
    split_payment = (
        len(matched_rows) > 1
        and len({(row.get("payment_sequential"), row.get("payment_type")) for row in matched_rows})
        > 1
    )

    if has_failed:
        verdict = "refund_failed"
    elif has_pending:
        verdict = "refund_pending"
    elif completed_refunds:
        verdict = "refunded"
    elif has_mismatch:
        verdict = "capture_mismatch"
    elif captured is None or expected is None:
        verdict = "insufficient_evidence"
    elif captured > expected and len(captures) > 1:
        verdict = "duplicate_capture"
    elif captured > expected:
        verdict = "capture_mismatch"
    else:
        verdict = "reconciled"

    confidence = 0.94 if captured is not None and expected is not None else 0.72 if refs else 0.2
    if unresolved:
        confidence = min(confidence, 0.65)
    return AgentResult(
        case_id=task.case_id,
        actor="payment-refund",
        status="completed" if refs else "partial",
        findings={
            "payment_analysis": {
                "verdict": verdict,
                "captured_total_brl": number(captured),
                "refunded_total_brl": number(refunded),
                "refundable_total_brl": number(refundable),
            },
            "affected_entities": {"payment_references": []},
            "split_payment": split_payment,
            "captured_events": captures,
            "refund_events": refund_events,
            "expected_total_brl": number(expected),
            "conflicts": [],
        },
        evidence_refs=tuple(dict.fromkeys(refs)),
        confidence=confidence,
        unresolved=tuple(unresolved),
    )
