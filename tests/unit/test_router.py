from __future__ import annotations

from student_agent.orchestration.router import Router


def test_router_selects_only_relevant_specialists() -> None:
    case = {
        "case_id": "L3B_CASE_001",
        "policy_version": "EC_POLICY_V2",
        "customer_request": {
            "claims": [
                {"claim_id": "claim-a", "topic": "late_delivery_logistics"},
                {"claim_id": "claim-b", "topic": "requested_full_refund"},
            ]
        },
    }

    plan = Router().plan(case)

    assert plan.agents == (
        "entity-agent",
        "order-product-agent",
        "shipment-agent",
        "payment-refund-agent",
        "policy-agent",
    )
