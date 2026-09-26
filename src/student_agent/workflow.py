from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .agent_contracts import AgentResult, AgentTask, validate_handoff
from .agents import entity_customer, order_fulfillment, payment_refund, policy_verifier
from .case_evidence import CaseEvidenceGateway
from .mcp_gateway import EvidenceGateway
from .planner import CAPABILITY_BY_ACTOR, build_execution_plan
from .trace import TraceWriter

AgentHandler = Callable[[AgentTask, CaseEvidenceGateway, TraceWriter], Awaitable[AgentResult]]
ENTITY_ID_FIELDS = ("order_ids", "item_ids", "seller_ids", "payment_references", "shipment_ids")
OUTPUT_FIELD_OWNERS: dict[str, frozenset[str]] = {
    "entity-customer": frozenset({"entity_resolution", "customer_context", "affected_entities"}),
    "order-fulfillment": frozenset({"shipment_analysis", "affected_entities"}),
    "payment-refund": frozenset({"payment_analysis", "affected_entities"}),
    "policy-verifier": frozenset(
        {
            "assessment",
            "claim_assessments",
            "root_cause_analysis",
            "data_conflicts",
            "financial_resolution",
            "resolution_actions",
        }
    ),
}
OUTPUT_FIELDS = frozenset().union(*OUTPUT_FIELD_OWNERS.values())
AGENT_MODULES: dict[str, Any] = {
    "entity-customer": entity_customer,
    "order-fulfillment": order_fulfillment,
    "payment-refund": payment_refund,
    "policy-verifier": policy_verifier,
}
RESULT_ALIASES = {
    "entity-customer": "entity",
    "order-fulfillment": "fulfillment",
    "payment-refund": "finance",
    "policy-verifier": "decision",
}
HANDOFF_FINDINGS = {
    "entity-customer": (
        "entity_resolution",
        "customer_context",
        "order_snapshot",
        "next_purchase_at",
    )
}


def _questions(case: Mapping[str, Any]) -> tuple[str, ...]:
    request = case.get("customer_request", {})
    if not isinstance(request, Mapping):
        return ()
    claims = request.get("claims", [])
    if not isinstance(claims, list):
        return ()
    return tuple(
        claim["topic"]
        for claim in claims
        if isinstance(claim, Mapping) and isinstance(claim.get("topic"), str) and claim["topic"]
    )


async def _dispatch(
    task: AgentTask,
    handler: AgentHandler,
    gateway: CaseEvidenceGateway,
    trace: TraceWriter,
) -> AgentResult:
    trace.emit(
        case_id=task.case_id,
        event_type="task_assigned",
        actor="coordinator",
        target=task.target,
    )
    result = await handler(task, gateway, trace)
    validate_handoff(task, result)
    trace.emit(
        case_id=task.case_id,
        event_type="handoff",
        actor=task.target,
        target="coordinator",
        attributes={"status": result.status},
    )
    return result


def _scope_for(actor: str, results: Mapping[str, AgentResult]) -> dict[str, Any]:
    """Build handoff scope from declared capability dependencies."""

    profile = CAPABILITY_BY_ACTOR[actor]
    scope: dict[str, Any] = {}
    for dependency in profile.dependencies:
        result = results.get(dependency)
        if result is None:
            raise ValueError(f"{actor} is missing dependency result {dependency}")
        scope[RESULT_ALIASES[dependency]] = result
        for field in HANDOFF_FINDINGS.get(dependency, ()):
            if field in result.findings:
                scope[field] = result.findings[field]
    return scope


def _merge_affected_entities(target: dict[str, list[str]], partial: Mapping[str, Any]) -> None:
    for field, identifiers in partial.items():
        if field not in target or not isinstance(identifiers, (list, tuple)):
            raise ValueError(f"invalid affected_entities field: {field}")
        for identifier in identifiers:
            if not isinstance(identifier, str) or not identifier:
                raise ValueError(f"invalid identifier in affected_entities.{field}")
            if identifier not in target[field]:
                target[field].append(identifier)


def assemble_output(case_id: str, results: tuple[AgentResult, ...]) -> dict[str, Any]:
    """Merge owned output fields while retaining each agent's internal findings separately."""

    output: dict[str, Any] = {"schema_version": "day09-l3b-output-v2", "case_id": case_id}
    affected_entities: dict[str, list[str]] = {field: [] for field in ENTITY_ID_FIELDS}
    refs: list[str] = []
    for result in results:
        if result.case_id != case_id:
            raise ValueError("cannot assemble results from another case")
        owned_fields = OUTPUT_FIELD_OWNERS.get(result.actor)
        if owned_fields is None:
            raise ValueError(f"unexpected output actor: {result.actor}")
        for field, value in result.findings.items():
            if field in OUTPUT_FIELDS and field not in owned_fields:
                raise ValueError(f"{result.actor} does not own output field {field}")
            if field == "affected_entities":
                if not isinstance(value, Mapping):
                    raise ValueError("affected_entities must be a mapping")
                _merge_affected_entities(affected_entities, value)
            elif field in owned_fields:
                if field in output:
                    raise ValueError(f"output field {field} was provided more than once")
                output[field] = value
        for ref in result.evidence_refs:
            if ref not in refs:
                refs.append(ref)
    output["affected_entities"] = affected_entities
    output["evidence_refs"] = refs
    return output


async def solve_case(
    case: dict[str, Any], gateway: EvidenceGateway, trace: TraceWriter
) -> dict[str, Any]:
    """Plan, coordinate, assemble, and independently verify one case."""

    case_id = case.get("case_id")
    questions = _questions(case)
    plan = await build_execution_plan(case, gateway, OUTPUT_FIELDS)
    case_gateway = CaseEvidenceGateway(gateway, case_id)
    results: dict[str, AgentResult] = {}

    for step in plan:
        module = AGENT_MODULES.get(step.actor)
        handler = getattr(module, "investigate", None) if module is not None else None
        if not callable(handler):
            raise ValueError(f"no handler registered for planned actor {step.actor}")
        task = AgentTask(
            case_id=case_id,
            sender="coordinator",
            target=step.actor,
            case=case,
            scope=_scope_for(step.actor, results),
            questions=questions,
        )
        actor_gateway = case_gateway.for_tools(step.allowed_tools)
        results[step.actor] = await _dispatch(task, handler, actor_gateway, trace)

    missing = set(OUTPUT_FIELD_OWNERS) - set(results)
    if missing:
        raise ValueError(f"execution plan did not produce required agents: {sorted(missing)}")

    ordered_results = tuple(results[actor] for actor in OUTPUT_FIELD_OWNERS)
    draft = assemble_output(case_id, ordered_results)

    policy_task = AgentTask(
        case_id=case_id,
        sender="coordinator",
        target="policy-verifier",
        case=case,
        scope=_scope_for("policy-verifier", results),
        questions=questions,
    )
    policy_step = next(step for step in plan if step.actor == "policy-verifier")
    verification = await policy_verifier.verify_output(
        policy_task,
        draft,
        ordered_results,
        case_gateway.for_tools(policy_step.allowed_tools),
        trace,
    )
    if verification.case_id != case_id:
        raise ValueError("verification result belongs to another case")
    trace.emit(
        case_id=case_id,
        event_type="verification_completed",
        actor="policy-verifier",
        decision_code="passed" if verification.passed else "failed",
        attributes={"issue_count": len(verification.issues)},
    )
    if not verification.passed:
        codes = ", ".join(issue.code for issue in verification.issues)
        raise ValueError(f"case verification failed: {codes}")
    trace.contracts.validate_output(draft, f"outputs/{case_id}.json")
    return draft
