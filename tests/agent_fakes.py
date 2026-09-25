from __future__ import annotations

from typing import Any

from student_agent.agent_contracts import AgentTask


class FakeGateway:
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[str] = []
        self.evidence_domains = {
            result["evidence_ref"]: result["domain"] for result in responses.values()
        }

    async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
        assert case_id == "CASE_001"
        self.calls.append(tool_name)
        return self.responses[tool_name]


class FakeTrace:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, **event: Any) -> None:
        self.events.append(event)


def evidence(domain: str, data: Any, suffix: str) -> dict[str, Any]:
    return {"evidence_ref": "ev_" + suffix.ljust(24, "0"), "domain": domain, "data": data}


def task(
    target: str,
    *,
    case: dict[str, Any] | None = None,
    scope: dict[str, Any] | None = None,
    topic: str = "unsupported_claim",
) -> AgentTask:
    return AgentTask(
        case_id="CASE_001",
        sender="coordinator",
        target=target,
        case=case or {"case_id": "CASE_001"},
        scope=scope or {},
        questions=(topic,),
    )
