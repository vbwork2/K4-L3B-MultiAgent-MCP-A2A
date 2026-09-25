from __future__ import annotations

from typing import Any

from ..core.agent_result import AgentResult
from ..rules.source_precedence import select_source


class ConflictResolver:
    name = "conflict-resolver"

    def resolve(self, conflicts: list[dict[str, Any]]) -> AgentResult:
        resolved: list[dict[str, Any]] = []
        issues: list[str] = []
        for conflict in conflicts:
            sources = conflict.get("sources", [])
            selected = select_source(sources) if isinstance(sources, list) else None
            item = dict(conflict)
            item["selected_source"] = selected
            item["resolution_code"] = (
                "SOURCE_PRECEDENCE" if selected else "UNRESOLVED_SOURCE_CONFLICT"
            )
            resolved.append(item)
            if selected is None:
                issues.append(f"unresolved conflict: {conflict.get('field', 'unknown')}")
        return AgentResult(
            status="partial" if issues else "ok",
            data={"conflicts": resolved},
            evidence_refs=[],
            confidence=0.6 if issues else 0.9,
            issues=issues,
        )
