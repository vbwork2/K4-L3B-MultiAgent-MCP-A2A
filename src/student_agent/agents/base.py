from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.agent_result import AgentResult
from ..core.context import CaseContext
from ..core.messages import TaskMessage
from ..evidence.evidence_store import EvidenceStore
from ..evidence.tool_cache import ToolCache
from ..mcp_gateway import EvidenceGateway
from ..trace import TraceWriter


class BaseAgent(ABC):
    name = "base-agent"

    def __init__(
        self,
        gateway: EvidenceGateway,
        trace: TraceWriter,
        evidence_store: EvidenceStore,
        tool_cache: ToolCache,
    ) -> None:
        self.gateway = gateway
        self.trace = trace
        self.evidence_store = evidence_store
        self.tool_cache = tool_cache

    @abstractmethod
    async def run(self, message: TaskMessage, context: CaseContext) -> AgentResult:
        """Execute one bounded specialist task."""
