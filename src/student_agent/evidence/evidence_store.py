from __future__ import annotations

from typing import Any


class EvidenceStore:
    """Evidence container owned by exactly one case."""

    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self._items: dict[str, dict[str, Any]] = {}

    def add(self, evidence: dict[str, Any]) -> str:
        evidence_ref = evidence.get("evidence_ref")
        if not isinstance(evidence_ref, str) or not evidence_ref:
            raise ValueError("evidence must contain a non-empty evidence_ref")
        existing = self._items.get(evidence_ref)
        if existing is not None and existing != evidence:
            raise ValueError(f"evidence_ref {evidence_ref!r} has conflicting payloads")
        self._items[evidence_ref] = evidence
        return evidence_ref

    def get(self, evidence_ref: str) -> dict[str, Any]:
        try:
            return self._items[evidence_ref]
        except KeyError as exc:
            raise KeyError(f"unknown evidence_ref for {self.case_id}: {evidence_ref}") from exc

    def contains(self, evidence_ref: str) -> bool:
        return evidence_ref in self._items

    def refs(self) -> tuple[str, ...]:
        return tuple(self._items)
