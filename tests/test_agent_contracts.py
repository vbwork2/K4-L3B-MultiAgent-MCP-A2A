from __future__ import annotations

import pytest

from student_agent.agent_contracts import (
    AgentIssue,
    AgentResult,
    AgentTask,
    VerificationResult,
    validate_handoff,
)


def test_handoff_rejects_a_result_from_the_wrong_actor_or_case() -> None:
    case = {"case_id": "CASE_001"}
    task = AgentTask(case_id="CASE_001", sender="coordinator", target="entity-customer", case=case)
    wrong_actor = AgentResult(case_id="CASE_001", actor="payment-refund", status="completed")
    wrong_case = AgentResult(case_id="CASE_002", actor="entity-customer", status="completed")

    with pytest.raises(ValueError, match="actor"):
        validate_handoff(task, wrong_actor)
    with pytest.raises(ValueError, match="another case"):
        validate_handoff(task, wrong_case)


def test_task_rejects_a_case_payload_from_another_case() -> None:
    with pytest.raises(ValueError, match="task case"):
        AgentTask(
            case_id="CASE_001",
            sender="coordinator",
            target="entity-customer",
            case={"case_id": "CASE_002"},
        )


def test_verification_failure_must_identify_what_needs_repair() -> None:
    with pytest.raises(ValueError, match="at least one issue"):
        VerificationResult(case_id="CASE_001", passed=False)

    issue = AgentIssue(
        code="INVALID_SCOPE",
        field="affected_entities.order_ids",
        owner="entity-customer",
        message="The selected order was rejected",
    )
    failed = VerificationResult(case_id="CASE_001", passed=False, issues=(issue,))
    assert failed.issues[0].owner == "entity-customer"


def test_result_rejects_duplicate_or_malformed_evidence_references() -> None:
    ref = "ev_" + "a" * 24
    with pytest.raises(ValueError, match="unique"):
        AgentResult(
            case_id="CASE_001",
            actor="entity-customer",
            status="completed",
            evidence_refs=(ref, ref),
        )
    with pytest.raises(ValueError, match="public-format"):
        AgentResult(
            case_id="CASE_001",
            actor="entity-customer",
            status="completed",
            evidence_refs=("invented",),
        )
