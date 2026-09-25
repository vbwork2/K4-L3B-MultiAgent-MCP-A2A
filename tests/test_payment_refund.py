from __future__ import annotations

import asyncio

from agent_fakes import FakeGateway, FakeTrace, evidence, task
from student_agent.agent_contracts import AgentResult
from student_agent.agents.payment_refund import investigate


def test_two_valid_captures_are_a_reconciled_split_payment() -> None:
    gateway = FakeGateway(
        {
            "get_payment_timeline": evidence(
                "payment",
                {
                    "events": [
                        {
                            "event_at": "2018-01-02T00:00:00Z",
                            "event_type": "captured",
                            "status": "confirmed",
                            "amount_brl": 40,
                        },
                        {
                            "event_at": "2018-01-02T01:00:00Z",
                            "event_type": "captured",
                            "status": "confirmed",
                            "amount_brl": 50,
                        },
                    ],
                    "payments": [
                        {"payment_value": 40, "payment_sequential": 1, "payment_type": "voucher"},
                        {
                            "payment_value": 50,
                            "payment_sequential": 2,
                            "payment_type": "credit_card",
                        },
                    ],
                },
                "payment",
            ),
        }
    )
    fulfillment = AgentResult(
        case_id="CASE_001",
        actor="order-fulfillment",
        status="completed",
        findings={"expected_total_brl": 90.0},
    )
    scope = {
        "entity_resolution": {"resolved_order_ids": ["order-1"]},
        "order_snapshot": {"order_purchase_timestamp": "2018-01-01T00:00:00Z"},
        "fulfillment": fulfillment,
    }
    result = asyncio.run(
        investigate(
            task("payment-refund", scope=scope, topic="valid_split_payment"),
            gateway,
            FakeTrace(),
        )
    )

    assert result.findings["payment_analysis"]["captured_total_brl"] == 90.0
    assert result.findings["payment_analysis"]["verdict"] == "reconciled"
    assert result.findings["split_payment"] is True
    assert gateway.calls == ["get_payment_timeline"]
