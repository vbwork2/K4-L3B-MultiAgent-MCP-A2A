from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskMessage:
    """Observable task envelope; reasoning text must never be placed here."""

    task_id: str
    case_id: str
    source: str
    target: str
    task_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    attempt: int = 1

    def __post_init__(self) -> None:
        required = (self.task_id, self.case_id, self.source, self.target, self.task_type)
        if any(not value for value in required):
            raise ValueError("task message identifiers must be non-empty")
        if self.attempt < 1:
            raise ValueError("attempt must be at least 1")
