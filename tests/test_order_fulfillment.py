from __future__ import annotations

import asyncio

from agent_fakes import FakeGateway, FakeTrace, evidence, task
from student_agent.agents.order_fulfillment import investigate


def test_fulfillment_scopes_items_and_attributes_confirmed_delay() -> None:
    gateway = FakeGateway(
        {
            "get_order_items": evidence(
                "item",
                [
                    {
                        "order_item_id": "item-old",
                        "seller_id": "seller-1",
                        "price": 80,
                        "freight_value": 10,
                        "shipping_limit_date": "2018-01-03T00:00:00Z",
                    },
                    {
                        "order_item_id": "item-future",
                        "seller_id": "seller-2",
                        "price": 100,
                        "freight_value": 20,
                        "shipping_limit_date": "2018-05-03T00:00:00Z",
                    },
                ],
                "items",
            ),
            "get_shipment_summary": evidence(
                "shipment",
                {
                    "events": [
                        {
                            "event_at": "2018-01-10T00:00:00Z",
                            "event_type": "delivered_late",
                            "status": "confirmed",
                            "actor": "logistics_provider",
                        }
                    ]
                },
                "shipment",
            ),
        }
    )
    scope = {
        "entity_resolution": {"resolved_order_ids": ["order-1"]},
        "order_snapshot": {
            "order_purchase_timestamp": "2018-01-01T00:00:00Z",
            "order_delivered_carrier_date": "2018-01-04T00:00:00Z",
            "order_delivered_customer_date": "2018-01-10T00:00:00Z",
            "order_estimated_delivery_date": "2018-01-08T00:00:00Z",
        },
        "next_purchase_at": "2018-05-01T00:00:00Z",
    }
    result = asyncio.run(investigate(task("order-fulfillment", scope=scope), gateway, FakeTrace()))

    assert result.findings["expected_total_brl"] == 90.0
    assert result.findings["affected_entities"]["item_ids"] == ["item-old"]
    assert result.findings["shipment_analysis"]["verdict"] == "logistics_delay"
    assert gateway.calls == ["get_order_items", "get_shipment_summary"]
