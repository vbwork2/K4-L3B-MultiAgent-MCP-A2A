from __future__ import annotations

import asyncio

import pytest

from agent_fakes import FakeGateway, FakeTrace, evidence, task
from student_agent.agent_contracts import AgentResult
from student_agent.agents.policy_verifier import _claim_refs, investigate


@pytest.mark.parametrize(
    ("primary_topic", "expected_domains"),
    [
        (
            "late_delivery_logistics",
            {"customer", "order", "item", "shipment", "payment", "policy"},
        ),
        (
            "late_delivery_seller",
            {"customer", "order", "item", "shipment", "seller", "payment", "policy"},
        ),
        (
            "canceled_order_paid",
            {"customer", "order", "item", "shipment", "payment", "policy"},
        ),
    ],
)
def test_full_refund_links_causal_and_amount_evidence(
    primary_topic: str, expected_domains: set[str]
) -> None:
    domains = {
        f"ev_{domain.ljust(24, '0')}": domain
        for domain in (
            "customer",
            "order",
            "item",
            "shipment",
            "seller",
            "product",
            "payment",
            "policy",
        )
    }
    results = (
        AgentResult(
            case_id="CASE_001",
            actor="entity-customer",
            status="completed",
            findings={},
            evidence_refs=tuple(domains),
        ),
    )
    refs = _claim_refs("requested_full_refund", primary_topic, results, [], domains)

    assert {domains[ref] for ref in refs} == expected_domains


@pytest.mark.parametrize(
    ("captured", "full_claim_verdict"),
    [(100, "partially_supported"), (12, "supported")],
)
def test_policy_caps_refund_and_assesses_full_claim_by_amount(
    captured: int, full_claim_verdict: str
) -> None:
    entity = AgentResult(
        case_id="CASE_001",
        actor="entity-customer",
        status="completed",
        findings={"entity_resolution": {"status": "resolved", "resolved_order_ids": ["order-1"]}},
        confidence=0.9,
    )
    fulfillment = AgentResult(
        case_id="CASE_001",
        actor="order-fulfillment",
        status="completed",
        findings={
            "shipment_analysis": {"verdict": "logistics_delay"},
            "affected_entities": {"seller_ids": []},
        },
        confidence=0.9,
    )
    finance = AgentResult(
        case_id="CASE_001",
        actor="payment-refund",
        status="completed",
        findings={
            "payment_analysis": {
                "verdict": "reconciled",
                "captured_total_brl": captured,
                "refundable_total_brl": 12,
            }
        },
        confidence=0.9,
    )
    gateway = FakeGateway(
        {
            "get_policy": evidence(
                "policy",
                {
                    "rules": {
                        "late_delivery_logistics": {
                            "case_status": "action_required",
                            "recommended_action": "refund_freight",
                            "refund_brl": 16,
                            "responsible_parties": [],
                        }
                    }
                },
                "policy",
            )
        }
    )
    case = {
        "case_id": "CASE_001",
        "policy_version": "EC_POLICY_V2",
        "customer_request": {
            "claims": [
                {"claim_id": "claim-1", "topic": "late_delivery_logistics"},
                {"claim_id": "claim-2", "topic": "requested_full_refund"},
            ]
        },
    }
    scope = {"entity": entity, "fulfillment": fulfillment, "finance": finance}
    result = asyncio.run(
        investigate(
            task("policy-verifier", case=case, scope=scope, topic="late_delivery_logistics"),
            gateway,
            FakeTrace(),
        )
    )

    assert result.findings["assessment"]["primary_issue"] == "late_delivery_logistics"
    assert result.findings["financial_resolution"]["recommended_refund_brl"] == 12.0
    assert result.findings["claim_assessments"][1]["verdict"] == full_claim_verdict
    assert result.findings["resolution_actions"] == ["refund_freight"]


def test_unsupported_issue_marks_customer_claim_unsupported() -> None:
    entity = AgentResult(
        case_id="CASE_001",
        actor="entity-customer",
        status="completed",
        findings={"entity_resolution": {"status": "resolved", "resolved_order_ids": ["order-1"]}},
        confidence=0.9,
    )
    fulfillment = AgentResult(
        case_id="CASE_001",
        actor="order-fulfillment",
        status="completed",
        findings={"shipment_analysis": {"verdict": "on_time"}, "order_status": "delivered"},
        confidence=0.9,
    )
    finance = AgentResult(
        case_id="CASE_001",
        actor="payment-refund",
        status="completed",
        findings={"payment_analysis": {"verdict": "reconciled", "captured_total_brl": 10}},
        confidence=0.9,
    )
    gateway = FakeGateway(
        {
            "get_policy": evidence(
                "policy",
                {"rules": {"unsupported_claim": {"case_status": "no_action", "refund_brl": 0}}},
                "policy",
            )
        }
    )
    case = {
        "case_id": "CASE_001",
        "policy_version": "EC_POLICY_V2",
        "customer_request": {"claims": [{"claim_id": "claim-1", "topic": "unsupported_claim"}]},
    }
    scope = {"entity": entity, "fulfillment": fulfillment, "finance": finance}
    result = asyncio.run(
        investigate(task("policy-verifier", case=case, scope=scope), gateway, FakeTrace())
    )

    assert result.findings["assessment"]["primary_issue"] == "unsupported_claim"
    assert result.findings["claim_assessments"][0]["verdict"] == "unsupported"
