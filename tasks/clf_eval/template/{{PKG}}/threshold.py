"""Turning scores into {{POS}}/{{NEG}} decisions and choosing the threshold."""
from __future__ import annotations

from {{PKG}}.metrics import POSITIVE, precision_recall_f1

NEGATIVE = "{{NEG}}"


def predict(scores: list[float], threshold: float, positive: str = POSITIVE, negative: str = NEGATIVE) -> list[str]:
    """Label a score as positive when it is >= threshold."""
    return [positive if s >= threshold else negative for s in scores]


def sweep_thresholds(y_true: list[str], scores: list[float], candidates: list[float] | None = None,
                     positive: str = POSITIVE, negative: str = NEGATIVE) -> list[tuple[float, float, float, float]]:
    """Evaluate every candidate threshold (default: the sorted distinct scores) and return a list of
    (threshold, precision, recall, f1) tuples in ascending threshold order."""
    raise NotImplementedError


def best_threshold(y_true: list[str], scores: list[float], candidates: list[float] | None = None,
                   positive: str = POSITIVE, negative: str = NEGATIVE) -> float:
    """The threshold with the highest F1. On ties, the lowest such threshold."""
    raise NotImplementedError
