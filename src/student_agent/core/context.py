from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .exceptions import ToolBudgetExceeded


@dataclass(slots=True)
class CaseContext:
    """Mutable state isolated to one competition case."""

    case_id: str
    case: dict[str, Any]
    max_tool_calls: int = 12
    tool_calls: int = 0
    cache_hits: int = 0
    evidence_refs: set[str] = field(default_factory=set)

    @classmethod
    def from_case(cls, case: dict[str, Any], *, max_tool_calls: int = 12) -> CaseContext:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("case must contain a non-empty case_id")
        return cls(case_id=case_id, case=case, max_tool_calls=max_tool_calls)

    def reserve_tool_call(self) -> None:
        if self.tool_calls >= self.max_tool_calls:
            raise ToolBudgetExceeded(
                f"tool-call budget exhausted for {self.case_id}: {self.max_tool_calls}"
            )
        self.tool_calls += 1

    def register_evidence(self, evidence_ref: str) -> None:
        self.evidence_refs.add(evidence_ref)
