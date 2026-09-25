from __future__ import annotations

from ..core.agent_result import AgentResult
from ..core.context import CaseContext
from ..core.exceptions import AgentNotImplementedError
from ..core.messages import TaskMessage
from .base import BaseAgent


class EntityAgent(BaseAgent):
    name = "entity-agent"

    async def run(self, message: TaskMessage, context: CaseContext) -> AgentResult:
        raise AgentNotImplementedError("implement entity resolution in EntityAgent.run()")
