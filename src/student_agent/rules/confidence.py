from __future__ import annotations


def clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, value))


def reduce_confidence(value: float, *, penalty: float) -> float:
    if penalty < 0:
        raise ValueError("penalty must be non-negative")
    return clamp_confidence(value - penalty)
