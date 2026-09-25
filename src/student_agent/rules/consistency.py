from __future__ import annotations

from typing import Any


def find_consistency_issues(output: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    resolution = output.get("entity_resolution", {})
    resolved = set(resolution.get("resolved_order_ids", []))
    rejected = set(resolution.get("rejected_candidates", []))
    if resolved & rejected:
        issues.append("resolved orders and rejected candidates overlap")

    financial = output.get("financial_resolution", {})
    lines = financial.get("refund_lines", [])
    line_total = sum(line.get("amount_brl", 0) for line in lines if isinstance(line, dict))
    recommended = financial.get("recommended_refund_brl")
    if isinstance(recommended, int | float) and abs(line_total - recommended) > 0.01:
        issues.append("refund line total does not match recommended refund")
    return issues
