from __future__ import annotations

from ..core.agent_result import AgentResult
from ..core.context import CaseContext
from ..core.exceptions import AgentNotImplementedError
from ..core.messages import TaskMessage
from .base import BaseAgent


class PaymentRefundAgent(BaseAgent):
    name = "payment-refund-agent"

    async def run(self, message: TaskMessage, context: CaseContext) -> AgentResult:
        raise AgentNotImplementedError(
            "implement payment and refund analysis in PaymentRefundAgent.run()"
        )
