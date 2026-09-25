from __future__ import annotations

from typing import Any

from .mcp_gateway import EvidenceGateway
from .orchestration.coordinator import Coordinator
from .trace import TraceWriter


async def solve_case(
    case: dict[str, Any], gateway: EvidenceGateway, trace: TraceWriter
) -> dict[str, Any]:
    """Run one case through the coordinator and specialist-agent workflow."""

    coordinator = Coordinator(gateway, trace)
    return await coordinator.solve(case)
