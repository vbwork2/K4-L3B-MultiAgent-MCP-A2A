from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from student_agent.agent_contracts import AgentResult, AgentTask
from student_agent.agents import entity_customer, order_fulfillment, payment_refund, policy_verifier
from student_agent.contracts import Contracts
from student_agent.trace import TraceWriter
from student_agent.workflow import solve_case


class FakeGateway:
    async def list_tools(self) -> list[str]:
        return []


def test_coordinator_handoffs_assemble_a_verified_l3b_output(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    case_id = "CASE_001"

    def handler(result: AgentResult):
        async def run(task: AgentTask, gateway: Any, trace: TraceWriter) -> AgentResult:
            del gateway, trace
            calls.append((task.target, dict(task.scope)))
            return result

        return run

    monkeypatch.setattr(
        entity_customer,
        "investigate",
        handler(
            AgentResult(
                case_id=case_id,
                actor="entity-customer",
                status="completed",
                findings={
                    "entity_resolution": {
                        "status": "resolved",
                        "resolved_order_ids": ["order-1"],
                        "rejected_candidates": [],
                        "confidence": 0.9,
                    },
                    "customer_context": {
                        "customer_unique_id": "customer-1",
                        "related_order_ids": [],
                    },
                    "affected_entities": {"order_ids": ["order-1"]},
                    "order_snapshot": {"order_purchase_timestamp": "2018-01-01T00:00:00Z"},
                },
                confidence=0.9,
            )
        ),
    )
    monkeypatch.setattr(
        order_fulfillment,
        "investigate",
        handler(
            AgentResult(
                case_id=case_id,
                actor="order-fulfillment",
                status="completed",
                findings={
                    "shipment_analysis": {
                        "verdict": "on_time",
                        "late_seller_ids": [],
                        "timeline_complete": True,
                    },
                    "affected_entities": {"item_ids": ["item-1"], "seller_ids": ["seller-1"]},
                    "expected_total_brl": 10.0,
                    "order_status": "delivered",
                },
                confidence=0.9,
            )
        ),
    )
    monkeypatch.setattr(
        payment_refund,
        "investigate",
        handler(
            AgentResult(
                case_id=case_id,
                actor="payment-refund",
                status="completed",
                findings={
                    "payment_analysis": {
                        "verdict": "reconciled",
                        "captured_total_brl": 10.0,
                        "refunded_total_brl": 0.0,
                        "refundable_total_brl": 10.0,
                    },
                    "affected_entities": {"payment_references": []},
                },
                confidence=0.9,
            )
        ),
    )
    monkeypatch.setattr(
        policy_verifier,
        "investigate",
        handler(
            AgentResult(
                case_id=case_id,
                actor="policy-verifier",
                status="completed",
                findings={
                    "assessment": {
                        "primary_issue": "valid_split_payment",
                        "secondary_issues": [],
                        "case_status": "no_action",
                        "confidence": 0.9,
                    },
                    "root_cause_analysis": {"ranked_causes": [], "responsible_parties": []},
                    "data_conflicts": [],
                    "financial_resolution": {
                        "currency": "BRL",
                        "recommended_refund_brl": 0.0,
                        "refund_lines": [],
                    },
                    "resolution_actions": ["document_no_action"],
                },
                confidence=0.9,
            )
        ),
    )

    contracts = Contracts(Path(__file__).resolve().parents[1] / "contracts" / "schemas")
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceWriter(trace_path, contracts)
    case = {"case_id": case_id, "customer_request": {"claims": [{"topic": "valid_split_payment"}]}}
    output = asyncio.run(solve_case(case, FakeGateway(), trace))
    contracts.validate_output(output, "assembled output")

    assert [actor for actor, _ in calls] == [
        "entity-customer",
        "order-fulfillment",
        "payment-refund",
        "policy-verifier",
    ]
    assert calls[1][1]["entity_resolution"]["resolved_order_ids"] == ["order-1"]
    assert output["affected_entities"]["item_ids"] == ["item-1"]
    assert output["assessment"]["primary_issue"] == "valid_split_payment"
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [event["event_type"] for event in events] == [
        "task_assigned",
        "handoff",
        "task_assigned",
        "handoff",
        "task_assigned",
        "handoff",
        "task_assigned",
        "handoff",
        "verification_completed",
    ]
