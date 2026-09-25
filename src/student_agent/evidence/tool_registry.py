from __future__ import annotations


class ToolRegistry:
    """Exact tool names discovered from the MCP server."""

    def __init__(self, tool_names: list[str]) -> None:
        self._names = frozenset(tool_names)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._names))

    def require(self, tool_name: str) -> str:
        if tool_name not in self._names:
            raise ValueError(f"MCP tool was not discovered: {tool_name}")
        return tool_name
