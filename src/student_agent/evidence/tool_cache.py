from __future__ import annotations

import json
from typing import Any


class ToolCache:
    """Per-case cache keyed by tool name and canonical arguments."""

    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self._items: dict[str, dict[str, Any]] = {}

    def _key(self, tool_name: str, arguments: dict[str, Any]) -> str:
        payload = {"case_id": self.case_id, "tool": tool_name, "arguments": arguments}
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def get(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        return self._items.get(self._key(tool_name, arguments))

    def put(
        self, tool_name: str, arguments: dict[str, Any], evidence: dict[str, Any]
    ) -> None:
        self._items[self._key(tool_name, arguments)] = evidence
