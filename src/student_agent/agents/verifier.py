from __future__ import annotations

from typing import Any

from ..contracts import ContractError, Contracts
from ..core.agent_result import AgentResult
from ..rules.consistency import find_consistency_issues


class Verifier:
    name = "verifier"

    def __init__(self, contracts: Contracts) -> None:
        self.contracts = contracts

    def verify(self, output: dict[str, Any]) -> AgentResult:
        issues = find_consistency_issues(output)
        try:
            self.contracts.validate_output(output, "candidate output")
        except ContractError as exc:
            issues.append(str(exc))
        return AgentResult(
            status="error" if issues else "ok",
            data={"valid": not issues},
            evidence_refs=[],
            confidence=1.0,
            issues=issues,
        )
