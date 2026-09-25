from __future__ import annotations

import asyncio
from typing import Any

import pytest

from student_agent.case_evidence import CaseEvidenceGateway


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    async def list_tools(self) -> list[str]:
        return ["get_order", "get_payment"]

    async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
        self.calls.append((tool_name, case_id, arguments))
        return {"evidence_ref": "ev_" + "a" * 24, "data": {"status": "found"}}


def test_case_cache_prevents_duplicate_mcp_calls_and_isolates_the_case() -> None:
    async def scenario() -> None:
        gateway = FakeGateway()
        case_gateway = CaseEvidenceGateway(gateway, "CASE_001", max_calls=1)
        order_view = case_gateway.for_tools({"get_order"})
        first = await order_view.call("get_order", case_id="CASE_001", order_id="order-1")
        first["data"]["status"] = "modified"
        second = await case_gateway.call("get_order", case_id="CASE_001", order_id="order-1")

        assert second["data"]["status"] == "found"
        assert case_gateway.calls_made == 1
        assert case_gateway.cached_results == 1
        assert len(gateway.calls) == 1

        with pytest.raises(ValueError, match="across cases"):
            await case_gateway.call("get_order", case_id="CASE_002", order_id="order-1")
        with pytest.raises(PermissionError, match="permission"):
            await order_view.call("get_payment", case_id="CASE_001", order_id="order-1")
        with pytest.raises(RuntimeError, match="budget exhausted"):
            await case_gateway.call("get_order", case_id="CASE_001", order_id="order-2")

        assert len(gateway.calls) == 1

    asyncio.run(scenario())
