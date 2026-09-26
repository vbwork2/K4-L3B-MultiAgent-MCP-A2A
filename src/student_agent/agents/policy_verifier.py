"""Evidence-driven policy decision and independent output verification."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..agent_contracts import AgentIssue, AgentResult, AgentTask, VerificationResult
from ..agent_utils import ZERO, consume, money, number
from ..case_evidence import CaseEvidenceGateway
from ..planner import tokens
from ..trace import TraceWriter

SUPPORT_THRESHOLD = 0.66
PARTIAL_THRESHOLD = 0.40
FALLBACK_ISSUES = frozenset({"unsupported_claim", "insufficient_evidence"})


def _fact_signature(
    entity: AgentResult,
    fulfillment: AgentResult,
    finance: AgentResult,
) -> tuple[frozenset[str], bool]:
    """Build semantic facts only from specialist findings."""

    facts: set[str] = set()
    incomplete = False

    resolution = entity.findings.get("entity_resolution", {})
    if isinstance(resolution, Mapping):
        status = resolution.get("status")
        facts.update(tokens(status))
        if status != "resolved":
            incomplete = True
    else:
        incomplete = True

    order_status = fulfillment.findings.get("order_status")
    facts.update(tokens(order_status))
    if isinstance(order_status, str) and order_status:
        facts.add("order")

    shipment = fulfillment.findings.get("shipment_analysis", {})
    if isinstance(shipment, Mapping):
        shipment_tokens = set(tokens(shipment.get("verdict")))
        facts.update(shipment_tokens)
        if "delay" in shipment_tokens:
            facts.update({"late", "delivery", "shipment"})
        if shipment_tokens & {"lost", "returned"}:
            facts.update({"delivery", "shipment"})
        if "insufficient" in shipment_tokens:
            incomplete = True
    else:
        incomplete = True

    payment = finance.findings.get("payment_analysis", {})
    if isinstance(payment, Mapping):
        payment_tokens = set(tokens(payment.get("verdict")))
        facts.update(payment_tokens)
        if payment_tokens:
            facts.add("payment")
        if "capture" in payment_tokens:
            facts.add("charge")
        if "reconciled" in payment_tokens:
            facts.add("valid")
        if "insufficient" in payment_tokens:
            incomplete = True

        captured = money(payment.get("captured_total_brl"))
        refunded = money(payment.get("refunded_total_brl"))
        refundable = money(payment.get("refundable_total_brl"))
        if captured is not None and captured > ZERO:
            facts.update({"paid", "payment", "capture", "charge"})
        if refunded is not None and refunded > ZERO:
            facts.update({"refund", "refunded", "payment"})
        if refundable is not None and refundable > ZERO:
            facts.update({"refund", "refundable", "payment"})
    else:
        incomplete = True

    if finance.findings.get("split_payment"):
        facts.update({"split", "payment"})
        if "reconciled" in facts:
            facts.add("valid")

    return frozenset(facts), incomplete


def _is_refund_request(topic: str) -> bool:
    topic_tokens = tokens(topic)
    return "refund" in topic_tokens and any(token.startswith("request") for token in topic_tokens)


def _support_score(topic: str, facts: frozenset[str]) -> float:
    topic_tokens = set(tokens(topic))
    if not topic_tokens or topic_tokens & FALLBACK_ISSUES:
        return 0.0
    return len(topic_tokens & facts) / len(topic_tokens)


def _candidate_topics(
    claims: list[Any],
    rules: Mapping[str, Any],
) -> tuple[tuple[str, int], ...]:
    """Collect candidates from case claims and policy rule keys."""

    candidates: dict[str, int] = {}
    for claim in claims:
        if not isinstance(claim, Mapping):
            continue
        topic = claim.get("topic")
        if not isinstance(topic, str) or not topic or _is_refund_request(topic):
            continue
        candidates[topic] = max(candidates.get(topic, 0), 2)

    for topic in rules:
        if isinstance(topic, str) and topic and topic not in FALLBACK_ISSUES:
            candidates[topic] = max(candidates.get(topic, 0), 1)

    return tuple(candidates.items())


def _select_primary_issue(
    claims: list[Any],
    rules: Mapping[str, Any],
    facts: frozenset[str],
    incomplete: bool,
) -> tuple[str, float]:
    """Choose the issue whose semantic tokens are best supported by evidence."""

    candidates = _candidate_topics(claims, rules)
    ranked = sorted(
        (
            (_support_score(topic, facts), priority, -index, topic)
            for index, (topic, priority) in enumerate(candidates)
        ),
        reverse=True,
    )
    if ranked and ranked[0][0] >= SUPPORT_THRESHOLD:
        score, _, _, topic = ranked[0]
        return topic, score

    if incomplete:
        return "insufficient_evidence", 0.0
    return "unsupported_claim", 1.0


def _conflicts(results: tuple[AgentResult, ...]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        raw = result.findings.get("conflicts", [])
        if not isinstance(raw, list):
            continue
        for conflict in raw:
            if not isinstance(conflict, Mapping):
                continue
            field = str(conflict.get("field") or "")
            if field and field not in seen:
                selected.append(dict(conflict))
                seen.add(field)
            if len(selected) >= 5:
                return selected
    return selected


def _claim_refs(
    topic: str,
    primary_topic: str,
    results: tuple[AgentResult, ...],
    policy_refs: list[str],
    domains: Mapping[str, str],
) -> list[str]:
    """Link evidence using claim semantics instead of a topic lookup table."""

    semantic = set(tokens(topic)) | set(tokens(primary_topic))
    relevant = {"customer", "order", "item", "shipment", "policy"}
    if semantic & {
        "payment",
        "paid",
        "charge",
        "capture",
        "refund",
        "refunded",
        "refundable",
    }:
        relevant.update({"payment", "refund"})
    if "seller" in semantic:
        relevant.add("seller")
    if "product" in semantic:
        relevant.add("product")

    all_refs = [*(ref for result in results for ref in result.evidence_refs), *policy_refs]
    return list(dict.fromkeys(ref for ref in all_refs if domains.get(ref) in relevant))[:30]


def _claim_verdict(
    topic: str,
    facts: frozenset[str],
    incomplete: bool,
    payment: Mapping[str, Any],
    primary: str,
    recommended: Any,
) -> str:
    if _is_refund_request(topic):
        captured = money(payment.get("captured_total_brl"))
        if incomplete or captured is None:
            return "insufficient_evidence"
        if "pending" in tokens(primary):
            return "partially_supported"
        if recommended == ZERO:
            return "unsupported"
        return "supported" if recommended >= captured else "partially_supported"

    score = _support_score(topic, facts)
    if score >= SUPPORT_THRESHOLD:
        return "supported"
    if score >= PARTIAL_THRESHOLD:
        return "partially_supported"
    return "insufficient_evidence" if incomplete else "unsupported"


async def investigate(
    task: AgentTask,
    gateway: CaseEvidenceGateway,
    trace: TraceWriter,
) -> AgentResult:
    """Infer a supported issue from findings, then apply the corresponding policy."""

    entity = task.scope.get("entity")
    fulfillment = task.scope.get("fulfillment")
    finance = task.scope.get("finance")
    if not all(isinstance(value, AgentResult) for value in (entity, fulfillment, finance)):
        raise ValueError("policy task requires entity, fulfillment, and finance results")

    prior = (entity, fulfillment, finance)
    policy_version = task.case.get("policy_version")
    policy_data: Mapping[str, Any] = {}
    refs: list[str] = []
    unresolved: list[str] = []

    if isinstance(policy_version, str) and policy_version:
        try:
            policy = await consume(
                task,
                gateway,
                trace,
                "get_policy",
                policy_version=policy_version,
            )
            refs.append(policy["evidence_ref"])
            if isinstance(policy.get("data"), Mapping):
                policy_data = policy["data"]
        except RuntimeError:
            unresolved.append("Policy evidence was unavailable from MCP")

    request = task.case.get("customer_request", {})
    claims = request.get("claims", []) if isinstance(request, Mapping) else []
    claims = claims if isinstance(claims, list) else []
    raw_rules = policy_data.get("rules", {})
    rules = raw_rules if isinstance(raw_rules, Mapping) else {}

    facts, incomplete = _fact_signature(entity, fulfillment, finance)
    primary, support_score = _select_primary_issue(claims, rules, facts, incomplete)
    raw_rule = rules.get(primary, {})
    rule = raw_rule if isinstance(raw_rule, Mapping) else {}

    default_status = "needs_investigation" if primary == "insufficient_evidence" else "no_action"
    status = rule.get("case_status", default_status)
    if status not in {"action_required", "no_action", "needs_investigation"}:
        status = "needs_investigation"

    action = rule.get("recommended_action")
    recommended = money(rule.get("refund_brl")) or ZERO
    payment = finance.findings.get("payment_analysis", {})
    if not isinstance(payment, Mapping):
        payment = {}

    refundable = money(payment.get("refundable_total_brl"))
    if refundable is not None:
        recommended = min(recommended, refundable)
    if primary == "insufficient_evidence":
        recommended = ZERO
        action = None

    order_ids = entity.findings.get("entity_resolution", {}).get("resolved_order_ids", [])
    order_id = order_ids[0] if isinstance(order_ids, list) and order_ids else None
    seller_ids = fulfillment.findings.get("affected_entities", {}).get("seller_ids", [])
    raw_parties = rule.get("responsible_parties", [])
    parties = raw_parties if isinstance(raw_parties, list) else []
    responsible_parties: list[dict[str, Any]] = []
    for party in parties[:5]:
        if not isinstance(party, Mapping):
            continue
        party_type = party.get("party_type", "unknown")
        party_id = party.get("party_id")
        if party_type == "seller" and seller_ids:
            party_id = seller_ids[0]
        responsible_parties.append({"party_type": party_type, "party_id": party_id})

    conflicts = _conflicts(prior)
    confidence = min(result.confidence for result in prior)
    if primary == "insufficient_evidence":
        confidence = min(confidence, 0.35)
    elif primary == "unsupported_claim":
        confidence = min(confidence, 0.72)
    else:
        confidence = min(confidence, 0.55 + 0.4 * support_score)
    if conflicts:
        confidence = min(confidence, 0.82)
    if unresolved:
        confidence = min(confidence, 0.45)

    claim_assessments: list[dict[str, Any]] = []
    for claim in claims[:5]:
        if not isinstance(claim, Mapping) or not isinstance(claim.get("claim_id"), str):
            continue
        topic = str(claim.get("topic") or "")
        claim_assessments.append(
            {
                "claim_id": claim["claim_id"],
                "verdict": _claim_verdict(
                    topic,
                    facts,
                    incomplete,
                    payment,
                    primary,
                    recommended,
                ),
                "confidence": confidence,
                "evidence_refs": _claim_refs(
                    topic,
                    primary,
                    prior,
                    refs,
                    gateway.evidence_domains,
                ),
            }
        )

    refund_lines = (
        [
            {
                "reason_code": primary.upper(),
                "amount_brl": number(recommended),
                "entity_id": order_id,
            }
        ]
        if recommended > ZERO
        else []
    )

    findings = {
        "assessment": {
            "primary_issue": primary,
            "secondary_issues": [],
            "case_status": status,
            "confidence": confidence,
        },
        "claim_assessments": claim_assessments,
        "root_cause_analysis": {
            "ranked_causes": (
                [{"cause_code": primary.upper(), "rank": 1}]
                if primary != "insufficient_evidence"
                else []
            ),
            "responsible_parties": responsible_parties,
        },
        "data_conflicts": conflicts,
        "financial_resolution": {
            "currency": "BRL",
            "recommended_refund_brl": number(recommended),
            "refund_lines": refund_lines,
        },
        "resolution_actions": [action] if isinstance(action, str) and action else [],
        "policy_rule": dict(rule),
    }

    trace.emit(
        case_id=task.case_id,
        event_type="policy_decided",
        actor="policy-verifier",
        decision_code=primary.upper(),
        evidence_refs=refs,
    )
    return AgentResult(
        case_id=task.case_id,
        actor="policy-verifier",
        status="completed" if refs else "partial",
        findings=findings,
        evidence_refs=tuple(refs),
        confidence=confidence,
        unresolved=tuple(unresolved),
    )


async def verify_output(
    task: AgentTask,
    draft: Mapping[str, Any],
    results: tuple[AgentResult, ...],
    gateway: CaseEvidenceGateway,
    trace: TraceWriter,
) -> VerificationResult:
    """Check schema, provenance, scope, arithmetic and semantic consistency."""

    issues: list[AgentIssue] = []

    def add(code: str, field: str, owner: str, message: str) -> None:
        issues.append(AgentIssue(code=code, field=field, owner=owner, message=message))

    try:
        trace.contracts.validate_output(draft, f"outputs/{task.case_id}.json")
    except ValueError as exc:
        add("SCHEMA_INVALID", "$", "coordinator", str(exc))

    if draft.get("case_id") != task.case_id:
        add("CASE_ID_MISMATCH", "case_id", "coordinator", "Draft case ID differs from task")

    by_actor = {result.actor: result for result in results}
    entity = by_actor.get("entity-customer")
    fulfillment = by_actor.get("order-fulfillment")
    finance = by_actor.get("payment-refund")
    if not all(isinstance(value, AgentResult) for value in (entity, fulfillment, finance)):
        add("MISSING_SPECIALIST", "$", "coordinator", "Required specialist result is missing")
        return VerificationResult(case_id=task.case_id, passed=False, issues=tuple(issues))

    known_refs = gateway.evidence_domains
    submitted_refs = draft.get("evidence_refs", [])
    if isinstance(submitted_refs, list):
        for ref in submitted_refs:
            if ref not in known_refs:
                add(
                    "UNKNOWN_EVIDENCE_REF",
                    "evidence_refs",
                    "coordinator",
                    "Ref is not from this case",
                )

    resolution = entity.findings.get("entity_resolution", {})
    if isinstance(resolution, Mapping):
        selected = set(resolution.get("resolved_order_ids", []))
        rejected = set(resolution.get("rejected_candidates", []))
        affected = draft.get("affected_entities", {})
        output_orders = (
            set(affected.get("order_ids", [])) if isinstance(affected, Mapping) else set()
        )
        if selected != output_orders or rejected & output_orders:
            add(
                "ENTITY_SCOPE",
                "affected_entities.order_ids",
                "coordinator",
                "Order scope is inconsistent",
            )

    financial = draft.get("financial_resolution", {})
    if isinstance(financial, Mapping):
        proposed = money(financial.get("recommended_refund_brl"))
        lines = financial.get("refund_lines", [])
        if proposed is not None and isinstance(lines, list):
            amounts = [money(line.get("amount_brl")) for line in lines if isinstance(line, Mapping)]
            if any(amount is None for amount in amounts) or sum(amounts, ZERO) != proposed:
                add(
                    "REFUND_TOTAL",
                    "financial_resolution",
                    "policy-verifier",
                    "Refund lines do not add up",
                )

    claim_assessments = draft.get("claim_assessments", [])
    if isinstance(claim_assessments, list):
        submitted = set(submitted_refs) if isinstance(submitted_refs, list) else set()
        for claim in claim_assessments:
            if isinstance(claim, Mapping) and not set(claim.get("evidence_refs", [])).issubset(
                submitted
            ):
                add(
                    "CLAIM_EVIDENCE",
                    "claim_assessments",
                    "policy-verifier",
                    "Claim ref is absent from output",
                )

    assessment = draft.get("assessment", {})
    if isinstance(assessment, Mapping):
        primary = assessment.get("primary_issue")
        if isinstance(primary, str) and primary not in FALLBACK_ISSUES:
            facts, incomplete = _fact_signature(entity, fulfillment, finance)
            if not incomplete and _support_score(primary, facts) < 0.60:
                add(
                    "PRIMARY_ISSUE_EVIDENCE",
                    "assessment.primary_issue",
                    "policy-verifier",
                    "Primary issue is not supported by specialist findings",
                )

    return VerificationResult(
        case_id=task.case_id,
        passed=not issues,
        issues=tuple(issues),
    )
