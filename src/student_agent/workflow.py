from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .agent_contracts import AgentResult, AgentTask, validate_handoff
from .agents import entity_customer, order_fulfillment, payment_refund, policy_verifier
from .case_evidence import CaseEvidenceGateway
from .mcp_gateway import EvidenceGateway
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
ACTOR_TOOLS = {
    "entity-customer": frozenset({"get_customer_history", "get_order"}),
    "order-fulfillment": frozenset(
        {"get_order_items", "get_shipment_summary", "get_product_context", "get_sellers"}
    ),
    "payment-refund": frozenset(
        {"get_payment_timeline", "get_refund_timeline"}
    ),
    "policy-verifier": frozenset({"get_policy"}),
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
    """Coordinate the four agents and verify the assembled output."""

    case_id = case.get("case_id")
    questions = _questions(case)
    entity_task = AgentTask(
        case_id=case_id,
        sender="coordinator",
        target="entity-customer",
        case=case,
        questions=questions,
    )
    case_gateway = CaseEvidenceGateway(gateway, case_id)
    available = set(await gateway.list_tools())
    actor_gateways = {
        actor: case_gateway.for_tools(tools & available) for actor, tools in ACTOR_TOOLS.items()
    }
    entity = await _dispatch(
        entity_task, entity_customer.investigate, actor_gateways["entity-customer"], trace
    )

    entity_scope = {
        key: entity.findings[key]
        for key in ("entity_resolution", "customer_context", "order_snapshot", "next_purchase_at")
        if key in entity.findings
    }
    fulfillment_task = AgentTask(
        case_id=case_id,
        sender="coordinator",
        target="order-fulfillment",
        case=case,
        scope=entity_scope,
        questions=questions,
    )
    fulfillment = await _dispatch(
        fulfillment_task,
        order_fulfillment.investigate,
        actor_gateways["order-fulfillment"],
        trace,
    )

    finance_task = AgentTask(
        case_id=case_id,
        sender="coordinator",
        target="payment-refund",
        case=case,
        scope={**entity_scope, "fulfillment": fulfillment},
        questions=questions,
    )
    finance = await _dispatch(
        finance_task, payment_refund.investigate, actor_gateways["payment-refund"], trace
    )

    policy_task = AgentTask(
        case_id=case_id,
        sender="coordinator",
        target="policy-verifier",
        case=case,
        scope={"entity": entity, "fulfillment": fulfillment, "finance": finance},
        questions=questions,
    )
    decision = await _dispatch(
        policy_task, policy_verifier.investigate, actor_gateways["policy-verifier"], trace
    )
    results = (entity, fulfillment, finance, decision)
    draft = assemble_output(case_id, results)
    verification = await policy_verifier.verify_output(
        policy_task, draft, results, actor_gateways["policy-verifier"], trace
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
