from __future__ import annotations

import asyncio

from student_agent.planner import assign_tools, build_execution_plan


class FakeGateway:
    async def list_tools(self) -> list[str]:
        return [
            "get_customer_history",
            "get_order",
            "get_order_items",
            "get_shipment_summary",
            "get_product_context",
            "get_sellers",
            "get_payment_timeline",
            "get_refund_timeline",
            "get_policy",
        ]

    async def describe_tools(self) -> list[dict[str, object]]:
        return [
            {"name": "get_customer_history", "description": "customer purchase history"},
            {"name": "get_order", "description": "order details"},
            {"name": "get_order_items", "description": "items in an order"},
            {"name": "get_shipment_summary", "description": "delivery shipment timeline"},
            {"name": "get_product_context", "description": "product details"},
            {"name": "get_sellers", "description": "seller records"},
            {"name": "get_payment_timeline", "description": "payment capture timeline"},
            {"name": "get_refund_timeline", "description": "refund transaction timeline"},
            {"name": "get_policy", "description": "policy rules and decision constraints"},
        ]


def test_assign_tools_from_discovered_metadata() -> None:
    descriptions = asyncio.run(FakeGateway().describe_tools())
    assigned = assign_tools(descriptions)

    assert {"get_customer_history", "get_order"} <= assigned["entity-customer"]
    assert {
        "get_order_items",
        "get_shipment_summary",
        "get_product_context",
        "get_sellers",
    } <= assigned["order-fulfillment"]
    assert {
        "get_payment_timeline",
        "get_refund_timeline",
    } <= assigned["payment-refund"]
    assert {"get_policy"} <= assigned["policy-verifier"]


def test_execution_plan_respects_capability_dependencies() -> None:
    required = frozenset(
        {
            "entity_resolution",
            "customer_context",
            "shipment_analysis",
            "payment_analysis",
            "assessment",
            "financial_resolution",
        }
    )
    case = {
        "case_id": "CASE_001",
        "customer_request": {"claims": [{"topic": "refund_failed"}]},
    }

    plan = asyncio.run(build_execution_plan(case, FakeGateway(), required))

    assert [step.actor for step in plan] == [
        "entity-customer",
        "order-fulfillment",
        "payment-refund",
        "policy-verifier",
    ]
    assert "get_refund_timeline" in plan[2].allowed_tools
    assert "get_policy" in plan[3].allowed_tools
