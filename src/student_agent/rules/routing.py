from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RoutingPlan:
    agents: tuple[str, ...]
    claim_topics: tuple[str, ...]


def build_routing_plan(case: dict[str, Any]) -> RoutingPlan:
    """Build a deterministic plan without interpreting free-form instructions."""

    request = case.get("customer_request")
    request = request if isinstance(request, dict) else {}
    claims = request.get("claims")
    claims = claims if isinstance(claims, list) else []
    topics = tuple(
        topic
        for claim in claims
        if isinstance(claim, dict)
        and isinstance((topic := claim.get("topic")), str)
        and topic
    )

    agents = ["entity-agent", "order-product-agent"]
    shipment_keywords = ("delivery", "shipment", "lost", "returned")
    if any(any(key in topic for key in shipment_keywords) for topic in topics):
        agents.append("shipment-agent")
    if any(
        any(key in topic for key in ("payment", "refund", "charge", "capture"))
        for topic in topics
    ):
        agents.append("payment-refund-agent")
    if case.get("policy_version") or any("requested_" in topic for topic in topics):
        agents.append("policy-agent")

    return RoutingPlan(agents=tuple(dict.fromkeys(agents)), claim_topics=topics)
