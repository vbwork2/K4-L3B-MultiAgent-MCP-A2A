"""Capability-driven execution planning for the L3B coordinator.

The planner deliberately avoids case-topic -> agent/tool lookup tables. It uses
agent capability vocabularies plus the MCP tool metadata discovered at runtime,
then builds a dependency-respecting plan from the output fields that must be
produced.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class AgentCapability:
    actor: str
    strong_terms: frozenset[str]
    weak_terms: frozenset[str]
    dependencies: tuple[str, ...]
    output_fields: frozenset[str]


@dataclass(frozen=True, slots=True)
class PlanStep:
    actor: str
    allowed_tools: frozenset[str]


CAPABILITIES: tuple[AgentCapability, ...] = (
    AgentCapability(
        actor="entity-customer",
        strong_terms=frozenset({"customer", "history", "identity", "entity", "candidate"}),
        weak_terms=frozenset({"order"}),
        dependencies=(),
        output_fields=frozenset({"entity_resolution", "customer_context"}),
    ),
    AgentCapability(
        actor="order-fulfillment",
        strong_terms=frozenset(
            {"item", "items", "shipment", "delivery", "seller", "product", "fulfillment"}
        ),
        weak_terms=frozenset({"order"}),
        dependencies=("entity-customer",),
        output_fields=frozenset({"shipment_analysis"}),
    ),
    AgentCapability(
        actor="payment-refund",
        strong_terms=frozenset(
            {"payment", "payments", "refund", "capture", "charge", "transaction", "finance"}
        ),
        weak_terms=frozenset({"order"}),
        dependencies=("entity-customer", "order-fulfillment"),
        output_fields=frozenset({"payment_analysis"}),
    ),
    AgentCapability(
        actor="policy-verifier",
        strong_terms=frozenset(
            {"policy", "rule", "decision", "verification", "verify", "conflict", "resolution"}
        ),
        weak_terms=frozenset(),
        dependencies=("entity-customer", "order-fulfillment", "payment-refund"),
        output_fields=frozenset(
            {
                "assessment",
                "claim_assessments",
                "root_cause_analysis",
                "data_conflicts",
                "financial_resolution",
                "resolution_actions",
            }
        ),
    ),
)

CAPABILITY_BY_ACTOR = {profile.actor: profile for profile in CAPABILITIES}


def tokens(value: Any) -> frozenset[str]:
    """Normalize names/descriptions/case text into comparison tokens."""

    if value is None:
        return frozenset()
    if isinstance(value, str):
        return frozenset(TOKEN_RE.findall(value.lower()))
    if isinstance(value, Mapping):
        merged: set[str] = set()
        for key, item in value.items():
            merged.update(tokens(key))
            merged.update(tokens(item))
        return frozenset(merged)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        merged: set[str] = set()
        for item in value:
            merged.update(tokens(item))
        return frozenset(merged)
    return frozenset()


def _tool_score(profile: AgentCapability, tool_tokens: frozenset[str]) -> int:
    return 3 * len(profile.strong_terms & tool_tokens) + len(profile.weak_terms & tool_tokens)


def assign_tools(tool_descriptions: Sequence[Mapping[str, Any]]) -> dict[str, frozenset[str]]:
    """Assign each discovered MCP tool to the best matching agent capability.

    Unknown tools remain unassigned instead of silently widening permissions.
    Ties are resolved by CAPABILITIES order, which keeps generic order lookups on
    the entity agent while more specific order/item/shipment tools naturally score
    higher for fulfillment.
    """

    assigned: dict[str, set[str]] = {profile.actor: set() for profile in CAPABILITIES}
    for description in tool_descriptions:
        name = description.get("name")
        if not isinstance(name, str) or not name:
            continue
        tool_tokens = tokens(
            (
                name,
                description.get("description", ""),
                description.get("input_schema", {}),
            )
        )
        ranked = [
            (_tool_score(profile, tool_tokens), index, profile.actor)
            for index, profile in enumerate(CAPABILITIES)
        ]
        score, _, actor = max(ranked, key=lambda item: (item[0], -item[1]))
        if score > 0:
            assigned[actor].add(name)
    return {actor: frozenset(names) for actor, names in assigned.items()}


async def discover_tools(gateway: Any) -> list[dict[str, Any]]:
    """Read tool metadata when available, otherwise fall back to discovered names."""

    describe = getattr(gateway, "describe_tools", None)
    if callable(describe):
        try:
            described = await describe()
        except (AttributeError, NotImplementedError):
            described = None
        if isinstance(described, list):
            normalized = [item for item in described if isinstance(item, Mapping)]
            if normalized:
                return [dict(item) for item in normalized]
    names = await gateway.list_tools()
    return [{"name": name, "description": "", "input_schema": {}} for name in names]


def _required_actors(required_output_fields: frozenset[str]) -> set[str]:
    required = {
        profile.actor for profile in CAPABILITIES if profile.output_fields & required_output_fields
    }
    changed = True
    while changed:
        changed = False
        for actor in tuple(required):
            for dependency in CAPABILITY_BY_ACTOR[actor].dependencies:
                if dependency not in required:
                    required.add(dependency)
                    changed = True
    return required


def _relevance(profile: AgentCapability, case_tokens: frozenset[str]) -> int:
    return 2 * len(profile.strong_terms & case_tokens) + len(profile.weak_terms & case_tokens)


def order_agents(required: set[str], case: Mapping[str, Any]) -> tuple[str, ...]:
    """Topologically order required agents, using case relevance only for ready ties."""

    remaining = set(required)
    completed: set[str] = set()
    ordered: list[str] = []
    case_tokens = tokens(case)
    while remaining:
        ready = [
            actor
            for actor in remaining
            if set(CAPABILITY_BY_ACTOR[actor].dependencies).issubset(completed)
        ]
        if not ready:
            raise ValueError("agent capability graph contains a dependency cycle")
        ready.sort(
            key=lambda actor: (
                -_relevance(CAPABILITY_BY_ACTOR[actor], case_tokens),
                next(i for i, profile in enumerate(CAPABILITIES) if profile.actor == actor),
            )
        )
        actor = ready[0]
        ordered.append(actor)
        completed.add(actor)
        remaining.remove(actor)
    return tuple(ordered)


async def build_execution_plan(
    case: Mapping[str, Any], gateway: Any, required_output_fields: frozenset[str]
) -> tuple[PlanStep, ...]:
    descriptions = await discover_tools(gateway)
    tool_permissions = assign_tools(descriptions)
    required = _required_actors(required_output_fields)
    actors = order_agents(required, case)
    return tuple(PlanStep(actor, tool_permissions.get(actor, frozenset())) for actor in actors)
