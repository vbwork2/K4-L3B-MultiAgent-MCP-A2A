from __future__ import annotations

from typing import Any

from ..rules.routing import RoutingPlan, build_routing_plan


class Router:
    def plan(self, case: dict[str, Any]) -> RoutingPlan:
        return build_routing_plan(case)
