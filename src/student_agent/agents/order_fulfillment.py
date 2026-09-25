"""Order and shipment investigation owned by Person 2."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from ..agent_contracts import AgentResult, AgentTask
from ..agent_utils import (
    ZERO,
    consume,
    in_window,
    moment,
    money,
    number,
    scoped_order,
    unique_strings,
)
from ..case_evidence import CaseEvidenceGateway
from ..trace import TraceWriter


def _selected_rows(
    rows: list[Any], purchase_at: Any, next_purchase_at: Any, date_field: str
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in rows
        if isinstance(row, Mapping)
        and (not purchase_at or in_window(row.get(date_field), purchase_at, next_purchase_at))
    ]


async def investigate(
    task: AgentTask, gateway: CaseEvidenceGateway, trace: TraceWriter
) -> AgentResult:
    """Inspect the verified order scope and return fulfillment findings."""

    order_id, snapshot, next_purchase = scoped_order(task)
    if not order_id:
        return AgentResult(
            case_id=task.case_id,
            actor="order-fulfillment",
            status="blocked",
            findings={
                "shipment_analysis": {
                    "verdict": "insufficient_evidence",
                    "late_seller_ids": [],
                    "timeline_complete": False,
                },
                "affected_entities": {},
                "expected_total_brl": None,
                "order_status": None,
                "conflicts": [],
            },
            unresolved=("No order was resolved for fulfillment investigation",),
        )

    refs: list[str] = []
    unresolved: list[str] = []
    conflicts: list[dict[str, Any]] = []
    purchase_at = snapshot.get("order_purchase_timestamp")
    raw_items: list[Any] = []
    shipment: Mapping[str, Any] = {}
    try:
        item_evidence = await consume(task, gateway, trace, "get_order_items", order_id=order_id)
        refs.append(item_evidence["evidence_ref"])
        if isinstance(item_evidence.get("data"), list):
            raw_items = item_evidence["data"]
    except RuntimeError:
        unresolved.append("Order items were unavailable from MCP")
    try:
        shipment_evidence = await consume(
            task, gateway, trace, "get_shipment_summary", order_id=order_id
        )
        refs.append(shipment_evidence["evidence_ref"])
        if isinstance(shipment_evidence.get("data"), Mapping):
            shipment = shipment_evidence["data"]
    except RuntimeError:
        unresolved.append("Shipment summary was unavailable from MCP")

    scope = task.case.get("investigation_scope", {})
    if isinstance(scope, Mapping) and scope.get("include_product_context"):
        try:
            product = await consume(task, gateway, trace, "get_product_context", order_id=order_id)
            refs.append(product["evidence_ref"])
        except RuntimeError:
            unresolved.append("Product context was unavailable from MCP")
    primary_topic = task.questions[0] if task.questions else ""
    if primary_topic in {"late_delivery_seller", "unavailable_order_paid"}:
        try:
            sellers = await consume(task, gateway, trace, "get_sellers", order_id=order_id)
            refs.append(sellers["evidence_ref"])
        except RuntimeError:
            unresolved.append("Seller records were unavailable from MCP")

    items = _selected_rows(raw_items, purchase_at, next_purchase, "shipping_limit_date")
    if raw_items and not items:
        unresolved.append("No item row matched the selected order period")
    item_ids = unique_strings([row.get("order_item_id") for row in items])
    seller_ids = unique_strings([row.get("seller_id") for row in items])
    expected_total: Decimal | None = ZERO if items else None
    for item in items:
        price = money(item.get("price"))
        freight = money(item.get("freight_value"))
        if price is None or freight is None:
            expected_total = None
            break
        expected_total += price + freight

    raw_limits = shipment.get("shipping_limits", [])
    limits = _selected_rows(
        raw_limits if isinstance(raw_limits, list) else [],
        purchase_at,
        next_purchase,
        "shipping_limit_at",
    )
    raw_events = shipment.get("events", [])
    events = _selected_rows(
        raw_events if isinstance(raw_events, list) else [], purchase_at, next_purchase, "event_at"
    )
    carrier_at = moment(snapshot.get("order_delivered_carrier_date"))
    delivered_at = moment(snapshot.get("order_delivered_customer_date"))
    estimated_at = moment(snapshot.get("order_estimated_delivery_date"))
    late_sellers = unique_strings(
        [
            row.get("seller_id")
            for row in limits
            if carrier_at is not None
            and moment(row.get("shipping_limit_at")) is not None
            and carrier_at > moment(row["shipping_limit_at"])
        ]
    )
    confirmed_late = [
        row
        for row in events
        if row.get("event_type") == "delivered_late" and row.get("status") == "confirmed"
    ]
    event_actor = confirmed_late[-1].get("actor") if confirmed_late else None
    status = str(snapshot.get("order_status") or "").lower()
    if status == "returned" or any(row.get("event_type") == "returned" for row in events):
        verdict = "returned"
    elif status == "lost" or any(row.get("event_type") == "lost" for row in events):
        verdict = "lost"
    elif event_actor == "seller":
        verdict = "seller_delay"
        late_sellers = late_sellers or seller_ids
    elif event_actor == "logistics_provider":
        verdict = "logistics_delay"
    elif delivered_at is not None and estimated_at is not None:
        if delivered_at > estimated_at:
            verdict = "seller_delay" if late_sellers else "logistics_delay"
        else:
            verdict = "on_time"
    else:
        verdict = "insufficient_evidence"

    summary_delivery = shipment.get("delivered_customer_at")
    snapshot_delivery = snapshot.get("order_delivered_customer_date")
    if summary_delivery and snapshot_delivery and summary_delivery != snapshot_delivery:
        conflicts.append(
            {
                "field": "shipment.delivered_customer_at",
                "sources": ["customer_history", "shipment_summary"],
                "selected_source": "customer_history",
                "resolution_code": "CASE_TIME_SCOPE",
            }
        )
    timeline_complete = all(
        value is not None for value in (moment(purchase_at), carrier_at, delivered_at, estimated_at)
    )
    confidence = 0.92 if timeline_complete else 0.75 if refs else 0.25
    if unresolved:
        confidence = min(confidence, 0.65)
    return AgentResult(
        case_id=task.case_id,
        actor="order-fulfillment",
        status="completed" if refs else "partial",
        findings={
            "shipment_analysis": {
                "verdict": verdict,
                "late_seller_ids": late_sellers,
                "timeline_complete": timeline_complete,
            },
            "affected_entities": {
                "item_ids": item_ids,
                "seller_ids": seller_ids,
                "shipment_ids": [],
            },
            "expected_total_brl": number(expected_total),
            "order_status": status,
            "selected_items": items,
            "shipment_events": events,
            "conflicts": conflicts,
        },
        evidence_refs=tuple(dict.fromkeys(refs)),
        confidence=confidence,
        unresolved=tuple(unresolved),
    )
