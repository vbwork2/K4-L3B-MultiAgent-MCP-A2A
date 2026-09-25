"""Case-scoped access to MCP evidence with a shared cache and call counter."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .agent_contracts import CASE_ID_PATTERN
from .mcp_gateway import EvidenceGateway


@dataclass(slots=True)
class _CaseState:
    gateway: EvidenceGateway
    case_id: str
    max_calls: int | None
    calls_made: int = 0
    cache: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class CaseEvidenceGateway:
    """Keep evidence and MCP call accounting inside one case."""

    def __init__(
        self,
        gateway: EvidenceGateway,
        case_id: str,
        *,
        max_calls: int | None = None,
        allowed_tools: frozenset[str] | None = None,
        _state: _CaseState | None = None,
    ) -> None:
        if not isinstance(case_id, str) or not CASE_ID_PATTERN.fullmatch(case_id):
            raise ValueError("case_id must match the public case ID format")
        if max_calls is not None and (
            isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 0
        ):
            raise ValueError("max_calls must be a non-negative integer or None")
        if allowed_tools is not None and any(
            not isinstance(name, str) or not name for name in allowed_tools
        ):
            raise ValueError("allowed_tools must contain non-empty tool names")
        self._state = _state or _CaseState(gateway, case_id, max_calls)
        if self._state.case_id != case_id:
            raise ValueError("a case evidence view cannot change case_id")
        self._allowed_tools = allowed_tools

    @property
    def calls_made(self) -> int:
        """Count actual tool calls, including calls that raised an error."""

        return self._state.calls_made

    @property
    def cached_results(self) -> int:
        return len(self._state.cache)

    @property
    def evidence_domains(self) -> dict[str, str]:
        """Map refs issued in this case to the domains in validated MCP responses."""

        return {
            evidence["evidence_ref"]: evidence["domain"] for evidence in self._state.cache.values()
        }

    def for_tools(self, allowed_tools: set[str] | frozenset[str]) -> CaseEvidenceGateway:
        """Create an actor view without widening an existing permission set."""

        names = frozenset(allowed_tools)
        if self._allowed_tools is not None and not names.issubset(self._allowed_tools):
            raise ValueError("a tool view cannot expand allowed tools")
        return CaseEvidenceGateway(
            self._state.gateway,
            self._state.case_id,
            max_calls=self._state.max_calls,
            allowed_tools=names,
            _state=self._state,
        )

    async def list_tools(self) -> list[str]:
        names = await self._state.gateway.list_tools()
        if self._allowed_tools is None:
            return names
        return [name for name in names if name in self._allowed_tools]

    async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
        if case_id != self._state.case_id:
            raise ValueError("MCP evidence cannot be used across cases")
        if self._allowed_tools is not None and tool_name not in self._allowed_tools:
            raise PermissionError(f"MCP tool {tool_name} is outside this agent's permission set")
        key = (tool_name, json.dumps(arguments, sort_keys=True, separators=(",", ":")))
        async with self._state.lock:
            cached = self._state.cache.get(key)
            if cached is not None:
                return deepcopy(cached)
            if (
                self._state.max_calls is not None
                and self._state.calls_made >= self._state.max_calls
            ):
                raise RuntimeError("case MCP call budget exhausted")
            self._state.calls_made += 1
            evidence = await self._state.gateway.call(tool_name, case_id=case_id, **arguments)
            self._state.cache[key] = deepcopy(evidence)
            return deepcopy(evidence)
