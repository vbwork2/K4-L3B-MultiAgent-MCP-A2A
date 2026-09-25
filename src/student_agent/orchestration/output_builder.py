from __future__ import annotations

from typing import Any

from ..core.agent_result import AgentResult
from ..core.exceptions import WorkflowError


class OutputBuilder:
    """Maps internal agent results to the public L3B output schema."""

    def build(self, case: dict[str, Any], results: dict[str, AgentResult]) -> dict[str, Any]:
        del case, results
        raise WorkflowError("implement L3B output mapping in OutputBuilder.build()")
