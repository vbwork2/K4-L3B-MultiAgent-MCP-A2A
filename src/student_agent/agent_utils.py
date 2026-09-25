"""Small evidence and time helpers shared by the specialist agents."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from .agent_contracts import AgentTask
from .case_evidence import CaseEvidenceGateway
from .trace import TraceWriter

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def moment(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def money(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def in_window(value: Any, start: Any, end: Any = None) -> bool:
    instant = moment(value)
    lower = moment(start)
    upper = moment(end)
    if instant is None or lower is None:
        return False
    try:
        return instant >= lower and (upper is None or instant < upper)
    except TypeError:
        return False


def unique_strings(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(value for value in values if isinstance(value, str) and value))


def scoped_order(task: AgentTask) -> tuple[str | None, Mapping[str, Any], str | None]:
    resolution = task.scope.get("entity_resolution", {})
    if not isinstance(resolution, Mapping):
        return None, {}, None
    ids = resolution.get("resolved_order_ids", [])
    order_id = ids[0] if isinstance(ids, list) and ids else None
    snapshot = task.scope.get("order_snapshot", {})
    if not isinstance(snapshot, Mapping):
        snapshot = {}
    next_purchase = task.scope.get("next_purchase_at")
    return order_id, snapshot, next_purchase if isinstance(next_purchase, str) else None


async def consume(
    task: AgentTask,
    gateway: CaseEvidenceGateway,
    trace: TraceWriter,
    tool_name: str,
    **arguments: str,
) -> dict[str, Any]:
    """Call one tool and record its evidence when an agent actually consumes it."""

    evidence = await gateway.call(tool_name, case_id=task.case_id, **arguments)
    trace.emit(
        case_id=task.case_id,
        event_type="tool_result_consumed",
        actor=task.target,
        tool_name=tool_name,
        evidence_refs=[evidence["evidence_ref"]],
    )
    return evidence
