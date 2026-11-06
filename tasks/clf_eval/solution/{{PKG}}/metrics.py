"""Binary classification metrics for {{POS}}/{{NEG}} labels."""
from __future__ import annotations

import math

POSITIVE = "{{POS}}"


def _check_lengths(a, b) -> None:
    if len(a) != len(b):
        raise ValueError(f"length mismatch: {len(a)} labels vs {len(b)} values")


def confusion_matrix(y_true: list[str], y_pred: list[str], positive: str = POSITIVE) -> dict[str, int]:
    """Return {"tp", "fp", "fn", "tn"} counts."""
    _check_lengths(y_true, y_pred)
    tp = fp = fn = tn = 0
    for t, p in zip(y_true, y_pred):
        if p == positive and t == positive:
            tp += 1
        elif p == positive and t != positive:
            fp += 1
        elif p != positive and t == positive:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def precision_recall_f1(y_true: list[str], y_pred: list[str], positive: str = POSITIVE) -> tuple[float, float, float]:
    """Precision, recall and F1 for the positive class. Undefined ratios (0/0) are reported as 0.0."""
    cm = confusion_matrix(y_true, y_pred, positive)
    precision = _safe_div(cm["tp"], cm["tp"] + cm["fp"])
    recall = _safe_div(cm["tp"], cm["tp"] + cm["fn"])
    f1 = _safe_div(2 * precision * recall, precision + recall)
    return precision, recall, f1


def auroc(y_true: list[str], scores: list[float], positive: str = POSITIVE) -> float:
    """Area under the ROC curve, rank-based (Mann-Whitney): the probability that a random {{POS}}
    {{ITEM}} scores higher than a random {{NEG}} one, with ties counted as half.

    Returns float('nan') if only one class is present.
    """
    _check_lengths(y_true, scores)
    pos = [s for t, s in zip(y_true, scores) if t == positive]
    neg = [s for t, s in zip(y_true, scores) if t != positive]
    if not pos or not neg:
        return math.nan
    total = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                total += 1.0
            elif p == n:
                total += 0.5
    return total / (len(pos) * len(neg))


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return math.nan
    return sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)
