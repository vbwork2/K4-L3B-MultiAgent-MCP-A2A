"""Shared messages used by the coordinator and specialist agents."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

Actor = Literal[
    "coordinator",
    "entity-customer",
    "order-fulfillment",
    "payment-refund",
    "policy-verifier",
]
ResultStatus = Literal["completed", "partial", "blocked"]

ACTORS: frozenset[str] = frozenset(
    {"coordinator", "entity-customer", "order-fulfillment", "payment-refund", "policy-verifier"}
)
RESULT_STATUSES: frozenset[str] = frozenset({"completed", "partial", "blocked"})
CASE_ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")
EVIDENCE_REF_PATTERN = re.compile(r"^ev_[A-Za-z0-9_-]{20,96}$")


def _check_case_id(case_id: str) -> None:
    if not isinstance(case_id, str) or not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("case_id must match the public case ID format")


def _check_actor(actor: str, label: str) -> None:
    if actor not in ACTORS:
        raise ValueError(f"{label} must be a known actor")


@dataclass(frozen=True, slots=True)
class AgentIssue:
    """A structured error or verification finding that can be routed to an owner."""

    code: str
    field: str
    owner: Actor
    message: str

    def __post_init__(self) -> None:
        for label in ("code", "field", "message"):
            value = getattr(self, label)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must be a non-empty string")
        _check_actor(self.owner, "owner")


@dataclass(frozen=True, slots=True)
class AgentTask:
    """One case-scoped request sent by the coordinator to an agent."""

    case_id: str
    sender: Actor
    target: Actor
    case: Mapping[str, Any]
    scope: Mapping[str, Any] = field(default_factory=dict)
    questions: tuple[str, ...] = ()
    query_budget: int | None = None

    def __post_init__(self) -> None:
        _check_case_id(self.case_id)
        _check_actor(self.sender, "sender")
        _check_actor(self.target, "target")
        if not isinstance(self.case, Mapping) or self.case.get("case_id") != self.case_id:
            raise ValueError("task case must match case_id")
        if not isinstance(self.scope, Mapping):
            raise ValueError("scope must be a mapping")
        if not isinstance(self.questions, tuple) or any(
            not isinstance(question, str) or not question.strip() for question in self.questions
        ):
            raise ValueError("questions must be a tuple of non-empty strings")
        if self.query_budget is not None and (
            isinstance(self.query_budget, bool)
            or not isinstance(self.query_budget, int)
            or self.query_budget < 0
        ):
            raise ValueError("query_budget must be a non-negative integer or None")


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Case-scoped findings returned by one specialist agent."""

    case_id: str
    actor: Actor
    status: ResultStatus
    findings: Mapping[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    confidence: float = 0.0
    unresolved: tuple[str, ...] = ()
    errors: tuple[AgentIssue, ...] = ()

    def __post_init__(self) -> None:
        _check_case_id(self.case_id)
        _check_actor(self.actor, "actor")
        if self.status not in RESULT_STATUSES:
            raise ValueError("status must be completed, partial, or blocked")
        if not isinstance(self.findings, Mapping):
            raise ValueError("findings must be a mapping")
        if not isinstance(self.confidence, (int, float)) or isinstance(self.confidence, bool):
            raise ValueError("confidence must be a number between zero and one")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between zero and one")
        if not isinstance(self.evidence_refs, tuple) or any(
            not isinstance(ref, str) or not EVIDENCE_REF_PATTERN.fullmatch(ref)
            for ref in self.evidence_refs
        ):
            raise ValueError("evidence_refs must contain public-format references")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must be unique")
        if not isinstance(self.unresolved, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.unresolved
        ):
            raise ValueError("unresolved must be a tuple of non-empty strings")
        if not isinstance(self.errors, tuple) or any(
            not isinstance(item, AgentIssue) for item in self.errors
        ):
            raise ValueError("errors must be a tuple of AgentIssue values")


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Independent checks on the coordinator's assembled draft output."""

    case_id: str
    passed: bool
    issues: tuple[AgentIssue, ...] = ()

    def __post_init__(self) -> None:
        _check_case_id(self.case_id)
        if not isinstance(self.passed, bool):
            raise ValueError("passed must be a boolean")
        if not isinstance(self.issues, tuple) or any(
            not isinstance(issue, AgentIssue) for issue in self.issues
        ):
            raise ValueError("issues must be a tuple of AgentIssue values")
        if self.passed and self.issues:
            raise ValueError("a passing verification cannot contain issues")
        if not self.passed and not self.issues:
            raise ValueError("a failed verification must contain at least one issue")


def validate_handoff(task: AgentTask, result: AgentResult) -> None:
    """Reject a result from another case or actor before passing it onward."""

    if result.case_id != task.case_id:
        raise ValueError("agent result belongs to another case")
    if result.actor != task.target:
        raise ValueError("agent result actor does not match the task target")
