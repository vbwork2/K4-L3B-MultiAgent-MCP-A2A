from __future__ import annotations

from typing import Any

from ..core.context import CaseContext
from ..core.exceptions import WorkflowError
from ..mcp_gateway import EvidenceGateway
from ..trace import TraceWriter
from .router import Router


class Coordinator:
    def __init__(self, gateway: EvidenceGateway, trace: TraceWriter) -> None:
        self.gateway = gateway
        self.trace = trace
        self.router = Router()

    async def solve(self, case: dict[str, Any]) -> dict[str, Any]:
        context = CaseContext.from_case(case)
        plan = self.router.plan(case)
        raise WorkflowError(
            f"agent execution is not implemented for {context.case_id}; "
            f"planned agents={list(plan.agents)}"
        )
