"""Entity and customer investigation owned by Person 1."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..agent_contracts import AgentResult, AgentTask
from ..agent_utils import consume, moment, unique_strings
from ..case_evidence import CaseEvidenceGateway
from ..trace import TraceWriter


def _purchase_key(row: Mapping[str, Any]) -> str:
    return str(row.get("order_purchase_timestamp") or "")


async def investigate(
    task: AgentTask, gateway: CaseEvidenceGateway, trace: TraceWriter
) -> AgentResult:
    """Resolve order candidates and return entity and customer findings."""

    request = task.case.get("customer_request", {})
    if not isinstance(request, Mapping):
        request = {}
    claimed = request.get("claimed_order_id")
    candidates = unique_strings([claimed, *task.case.get("candidate_order_ids", [])])
    hint = task.case.get("customer_unique_id_hint")
    refs: list[str] = []
    unresolved: list[str] = []
    orders: list[dict[str, Any]] = []
    customer_id: str | None = None

    if isinstance(hint, str) and hint:
        try:
            history = await consume(
                task, gateway, trace, "get_customer_history", customer_unique_id=hint
            )
            refs.append(history["evidence_ref"])
            data = history.get("data")
            if isinstance(data, Mapping):
                customer_id = data.get("customer_unique_id")
                raw_orders = data.get("orders", [])
                if isinstance(raw_orders, list):
                    orders = [dict(row) for row in raw_orders if isinstance(row, Mapping)]
        except RuntimeError:
            unresolved.append("Customer history was unavailable from MCP")

    matching = [row for row in orders if row.get("order_id") in candidates]
    opened = moment(task.case.get("opened_at"))
    past = [
        row
        for row in matching
        if opened is not None
        and moment(row.get("order_purchase_timestamp")) is not None
        and moment(row["order_purchase_timestamp"]) <= opened
    ]
    selected: dict[str, Any] | None = None
    if past:
        topic = task.questions[0] if task.questions else ""
        expected_status = {
            "canceled_order_paid": "canceled",
            "unavailable_order_paid": "unavailable",
        }.get(topic)
        status_matches = [
            row for row in past if expected_status and row.get("order_status") == expected_status
        ]
        selected = max(status_matches or past, key=_purchase_key)
    elif matching:
        selected = min(matching, key=_purchase_key)
        unresolved.append("No candidate purchase preceded the case opening time")

    authoritative: Mapping[str, Any] | None = None
    lookup_id = selected.get("order_id") if selected else claimed
    if isinstance(lookup_id, str) and lookup_id:
        try:
            order = await consume(task, gateway, trace, "get_order", order_id=lookup_id)
            refs.append(order["evidence_ref"])
            if isinstance(order.get("data"), Mapping):
                authoritative = order["data"]
        except RuntimeError:
            unresolved.append("The order lookup was unavailable from MCP")
    if selected is None and authoritative and authoritative.get("order_id") in candidates:
        selected = dict(authoritative)

    resolved_id = selected.get("order_id") if selected else None
    rejected = [candidate for candidate in candidates if candidate != resolved_id]
    next_purchase: str | None = None
    if selected:
        later = sorted(
            row["order_purchase_timestamp"]
            for row in matching
            if row.get("order_id") == resolved_id
            and _purchase_key(row) > _purchase_key(selected)
            and isinstance(row.get("order_purchase_timestamp"), str)
        )
        next_purchase = later[0] if later else None

    conflicts: list[dict[str, Any]] = []
    if selected and authoritative:
        history_purchase = selected.get("order_purchase_timestamp")
        order_purchase = authoritative.get("order_purchase_timestamp")
        if history_purchase and order_purchase and history_purchase != order_purchase:
            conflicts.append(
                {
                    "field": "order_purchase_timestamp",
                    "sources": ["customer_history", "get_order"],
                    "selected_source": "customer_history",
                    "resolution_code": "CASE_TIME_SCOPE",
                }
            )

    related = unique_strings(
        [row.get("order_id") for row in orders if row.get("order_id") != resolved_id]
    )
    confidence = 0.95 if selected and orders else 0.65 if selected else 0.1
    if conflicts:
        confidence = min(confidence, 0.85)
    if unresolved:
        confidence = min(confidence, 0.7)
    findings: dict[str, Any] = {
        "entity_resolution": {
            "status": "resolved" if selected else "not_found",
            "resolved_order_ids": [resolved_id] if isinstance(resolved_id, str) else [],
            "rejected_candidates": rejected,
            "confidence": confidence,
        },
        "customer_context": {
            "customer_unique_id": customer_id,
            "related_order_ids": related,
        },
        "affected_entities": {"order_ids": [resolved_id] if isinstance(resolved_id, str) else []},
        "order_snapshot": selected or {},
        "next_purchase_at": next_purchase,
        "conflicts": conflicts,
    }
    return AgentResult(
        case_id=task.case_id,
        actor="entity-customer",
        status="completed" if selected else "blocked",
        findings=findings,
        evidence_refs=tuple(dict.fromkeys(refs)),
        confidence=confidence,
        unresolved=tuple(unresolved),
    )
