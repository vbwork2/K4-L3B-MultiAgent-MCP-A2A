from __future__ import annotations

import asyncio

from agent_fakes import FakeGateway, FakeTrace, evidence, task
from student_agent.agents.entity_customer import investigate


def test_entity_selects_purchase_before_case_opened() -> None:
    old = {"order_id": "order-1", "order_purchase_timestamp": "2018-01-01T00:00:00Z"}
    future = {"order_id": "order-1", "order_purchase_timestamp": "2018-05-01T00:00:00Z"}
    gateway = FakeGateway(
        {
            "get_customer_history": evidence(
                "customer", {"customer_unique_id": "customer-1", "orders": [old, future]}, "history"
            ),
            "get_order": evidence("order", future, "order"),
        }
    )
    case = {
        "case_id": "CASE_001",
        "opened_at": "2018-02-01T00:00:00Z",
        "customer_unique_id_hint": "customer-1",
        "candidate_order_ids": ["order-1", "order-fake"],
        "customer_request": {"claimed_order_id": "order-1"},
    }
    result = asyncio.run(investigate(task("entity-customer", case=case), gateway, FakeTrace()))

    assert result.findings["order_snapshot"] == old
    assert result.findings["next_purchase_at"] == future["order_purchase_timestamp"]
    assert result.findings["entity_resolution"]["rejected_candidates"] == ["order-fake"]
    assert result.findings["conflicts"][0]["resolution_code"] == "CASE_TIME_SCOPE"
    assert gateway.calls == ["get_customer_history", "get_order"]


def test_entity_selects_evidenced_canceled_purchase_with_reused_order_id() -> None:
    canceled = {
        "order_id": "order-1",
        "order_purchase_timestamp": "2018-08-05T09:00:00Z",
        "order_status": "canceled",
    }
    delivered = {
        "order_id": "order-1",
        "order_purchase_timestamp": "2018-08-14T09:00:00Z",
        "order_status": "delivered",
    }
    gateway = FakeGateway(
        {
            "get_customer_history": evidence(
                "customer",
                {"customer_unique_id": "customer-1", "orders": [delivered, canceled]},
                "history",
            ),
            "get_order": evidence("order", delivered, "order"),
        }
    )
    case = {
        "case_id": "CASE_001",
        "opened_at": "2018-08-17T12:00:00Z",
        "customer_unique_id_hint": "customer-1",
        "candidate_order_ids": ["order-1"],
        "customer_request": {"claimed_order_id": "order-1"},
    }
    result = asyncio.run(
        investigate(
            task("entity-customer", case=case, topic="canceled_order_paid"),
            gateway,
            FakeTrace(),
        )
    )

    assert result.findings["order_snapshot"] == canceled
    assert result.findings["next_purchase_at"] == delivered["order_purchase_timestamp"]
    assert result.findings["conflicts"][0]["resolution_code"] == "CASE_TIME_SCOPE"
    assert gateway.calls == ["get_customer_history", "get_order"]
