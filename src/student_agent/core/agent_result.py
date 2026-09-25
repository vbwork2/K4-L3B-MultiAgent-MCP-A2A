from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AgentStatus = Literal["ok", "partial", "error", "skipped"]


@dataclass(slots=True)
class AgentResult:
    """The only result contract returned by every internal agent."""

    status: AgentStatus
    data: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 0.0
    issues: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence_refs must be unique")
        if any(not isinstance(issue, str) or not issue for issue in self.issues):
            raise ValueError("issues must contain non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        """Serialize with exactly the five fields agreed by the team."""

        return {
            "status": self.status,
            "data": self.data,
            "evidence_refs": self.evidence_refs,
            "confidence": self.confidence,
            "issues": self.issues,
        }
