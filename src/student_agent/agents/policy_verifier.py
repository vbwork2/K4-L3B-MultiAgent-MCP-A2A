"""Policy decisions and independent verification owned by Person 4."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..agent_contracts import AgentIssue, AgentResult, AgentTask, VerificationResult
from ..agent_utils import ZERO, consume, money, number
from ..case_evidence import CaseEvidenceGateway
from ..trace import TraceWriter


def _issue_supported(
    topic: str, entity: AgentResult, fulfillment: AgentResult, finance: AgentResult
) -> bool | None:
    resolution = entity.findings.get("entity_resolution", {})
    shipment = fulfillment.findings.get("shipment_analysis", {})
    payment = finance.findings.get("payment_analysis", {})
    if not isinstance(resolution, Mapping) or resolution.get("status") != "resolved":
        return None
    if not isinstance(shipment, Mapping) or not isinstance(payment, Mapping):
        return None
    order_status = fulfillment.findings.get("order_status")
    payment_verdict = payment.get("verdict")
    shipment_verdict = shipment.get("verdict")
    captured = money(payment.get("captured_total_brl"))
    checks: dict[str, bool | None] = {
        "late_delivery_logistics": shipment_verdict == "logistics_delay",
        "late_delivery_seller": shipment_verdict == "seller_delay",
        "valid_split_payment": payment_verdict == "reconciled"
        and bool(finance.findings.get("split_payment")),
        "payment_mismatch": payment_verdict == "capture_mismatch",
        "duplicate_charge": payment_verdict == "duplicate_capture",
        "refund_pending": payment_verdict == "refund_pending",
        "refund_failed": payment_verdict == "refund_failed",
        "canceled_order_paid": order_status == "canceled"
        and captured is not None
        and captured > ZERO,
        "unavailable_order_paid": order_status == "unavailable"
        and captured is not None
        and captured > ZERO,
        "unsupported_claim": shipment_verdict in {"on_time", "insufficient_evidence"}
        and payment_verdict == "reconciled"
        and order_status not in {"canceled", "unavailable"},
    }
    if (
        topic in {"late_delivery_logistics", "late_delivery_seller"}
        and shipment_verdict == "insufficient_evidence"
    ):
        return None
    if (
        topic
        in {
            "valid_split_payment",
            "payment_mismatch",
            "duplicate_charge",
            "refund_pending",
            "refund_failed",
            "canceled_order_paid",
            "unavailable_order_paid",
        }
        and payment_verdict == "insufficient_evidence"
    ):
        return None
    return checks.get(topic)


def _conflicts(results: tuple[AgentResult, ...]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        raw = result.findings.get("conflicts", [])
        if not isinstance(raw, list):
            continue
        for conflict in raw:
            if isinstance(conflict, Mapping) and conflict.get("field") not in seen:
                selected.append(dict(conflict))
                seen.add(str(conflict["field"]))
            if len(selected) >= 5:
                return selected
    return selected


def _claim_refs(
    topic: str, results: tuple[AgentResult, ...], policy_refs: list[str], domains: Mapping[str, str]
) -> list[str]:
    if topic.startswith("late_delivery"):
        relevant = {"customer", "order", "item", "shipment", "policy"}
    elif topic in {"payment_mismatch", "duplicate_charge", "valid_split_payment"}:
        relevant = {"customer", "item", "payment", "policy"}
    elif topic in {"refund_pending", "refund_failed", "requested_full_refund"}:
        relevant = {"payment", "refund", "policy", "item"}
    else:
        relevant = {"customer", "order", "shipment", "payment", "policy"}
    all_refs = [*(ref for result in results for ref in result.evidence_refs), *policy_refs]
    return list(dict.fromkeys(ref for ref in all_refs if domains.get(ref) in relevant))[:30]


async def investigate(
    task: AgentTask, gateway: CaseEvidenceGateway, trace: TraceWriter
) -> AgentResult:
    """Apply policy to prior findings and return decision fields."""

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
                task, gateway, trace, "get_policy", policy_version=policy_version
            )
            refs.append(policy["evidence_ref"])
            if isinstance(policy.get("data"), Mapping):
                policy_data = policy["data"]
        except RuntimeError:
            unresolved.append("Policy evidence was unavailable from MCP")

    request = task.case.get("customer_request", {})
    claims = request.get("claims", []) if isinstance(request, Mapping) else []
    claims = claims if isinstance(claims, list) else []
    topic = task.questions[0] if task.questions else ""
    support = _issue_supported(topic, entity, fulfillment, finance)
    primary = (
        topic
        if support and topic
        else "insufficient_evidence"
        if support is None
        else "unsupported_claim"
    )
    rules = policy_data.get("rules", {})
    rule = rules.get(primary, {}) if isinstance(rules, Mapping) else {}
    if not isinstance(rule, Mapping):
        rule = {}
    status = rule.get("case_status", "needs_investigation")
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
    parties = rule.get("responsible_parties", [])
    parties = parties if isinstance(parties, list) else []
    seller_ids = fulfillment.findings.get("affected_entities", {}).get("seller_ids", [])
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
    confidence = min(confidence, 0.93 if support else 0.72 if support is False else 0.35)
    if conflicts:
        confidence = min(confidence, 0.82)
    if unresolved:
        confidence = min(confidence, 0.45)
    claim_assessments: list[dict[str, Any]] = []
    for index, claim in enumerate(claims[:5]):
        if not isinstance(claim, Mapping) or not isinstance(claim.get("claim_id"), str):
            continue
        claim_refs = _claim_refs(
            str(claim.get("topic") or ""), prior, refs, gateway.evidence_domains
        )
        if index == 0:
            verdict = (
                "unsupported"
                if primary == "unsupported_claim"
                else "supported"
                if support
                else "insufficient_evidence"
                if support is None
                else "unsupported"
            )
        elif claim.get("topic") == "requested_full_refund":
            captured = money(payment.get("captured_total_brl"))
            if support is None or captured is None:
                verdict = "insufficient_evidence"
            elif primary == "refund_pending":
                verdict = "partially_supported"
            elif recommended == ZERO:
                verdict = "unsupported"
            elif recommended >= captured:
                verdict = "supported"
            else:
                verdict = "partially_supported"
        else:
            verdict = "insufficient_evidence"
        claim_assessments.append(
            {
                "claim_id": claim["claim_id"],
                "verdict": verdict,
                "confidence": confidence,
                "evidence_refs": claim_refs[:30],
            }
        )

    refund_lines = (
        [{"reason_code": primary.upper(), "amount_brl": number(recommended), "entity_id": order_id}]
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
    """Check the assembled draft independently before finalization."""

    issues: list[AgentIssue] = []

    def add(code: str, field: str, owner: str, message: str) -> None:
        issues.append(AgentIssue(code=code, field=field, owner=owner, message=message))

    try:
        trace.contracts.validate_output(draft, f"outputs/{task.case_id}.json")
    except ValueError as exc:
        add("SCHEMA_INVALID", "$", "coordinator", str(exc))
    if draft.get("case_id") != task.case_id:
        add("CASE_ID_MISMATCH", "case_id", "coordinator", "Draft case ID differs from task")
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
    entity = results[0]
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
        for claim in claim_assessments:
            if isinstance(claim, Mapping) and not set(claim.get("evidence_refs", [])).issubset(
                set(submitted_refs) if isinstance(submitted_refs, list) else set()
            ):
                add(
                    "CLAIM_EVIDENCE",
                    "claim_assessments",
                    "policy-verifier",
                    "Claim ref is absent from output",
                )
    return VerificationResult(case_id=task.case_id, passed=not issues, issues=tuple(issues))
