from __future__ import annotations

import pytest

from student_agent.core.agent_result import AgentResult


def test_agent_result_serializes_exact_contract() -> None:
    result = AgentResult(
        status="ok",
        data={"value": 1},
        evidence_refs=["ev_example"],
        confidence=0.8,
        issues=[],
    )

    assert result.to_dict() == {
        "status": "ok",
        "data": {"value": 1},
        "evidence_refs": ["ev_example"],
        "confidence": 0.8,
        "issues": [],
    }


def test_agent_result_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        AgentResult(status="ok", confidence=1.1)
