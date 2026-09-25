from __future__ import annotations

# Initial policy for team review. A domain-specific rule may override this table.
SOURCE_PRECEDENCE = {
    "policy": 100,
    "refund": 90,
    "payment": 80,
    "shipment": 70,
    "order": 60,
    "item": 50,
    "seller": 40,
    "product": 30,
    "customer": 20,
}


def select_source(sources: list[str]) -> str | None:
    known = [source for source in sources if source in SOURCE_PRECEDENCE]
    if not known:
        return None
    return max(known, key=SOURCE_PRECEDENCE.__getitem__)
