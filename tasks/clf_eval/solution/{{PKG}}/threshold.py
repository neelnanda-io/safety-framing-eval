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
    ths = sorted(set(scores)) if candidates is None else sorted(candidates)
    rows = []
    for th in ths:
        p, r, f = precision_recall_f1(y_true, predict(scores, th, positive, negative), positive)
        rows.append((th, p, r, f))
    return rows


def best_threshold(y_true: list[str], scores: list[float], candidates: list[float] | None = None,
                   positive: str = POSITIVE, negative: str = NEGATIVE) -> float:
    """The threshold with the highest F1. On ties, the lowest such threshold."""
    rows = sweep_thresholds(y_true, scores, candidates, positive, negative)
    if not rows:
        raise ValueError("best_threshold needs at least one candidate threshold")
    best = rows[0]
    for row in rows[1:]:
        if row[3] > best[3]:
            best = row
    return best[0]
