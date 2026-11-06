"""Binary classification metrics for {{POS}}/{{NEG}} labels."""
from __future__ import annotations

import math

POSITIVE = "{{POS}}"


def confusion_matrix(y_true: list[str], y_pred: list[str], positive: str = POSITIVE) -> dict[str, int]:
    """Return {"tp", "fp", "fn", "tn"} counts."""
    tp = fp = fn = tn = 0
    for t, p in zip(y_true, y_pred):
        if p == positive and t == positive:
            tp += 1
        elif p == positive and t != positive:
            fn += 1
        elif p != positive and t == positive:
            fp += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall_f1(y_true: list[str], y_pred: list[str], positive: str = POSITIVE) -> tuple[float, float, float]:
    """Precision, recall and F1 for the positive class. Undefined ratios (0/0) are reported as 0.0."""
    cm = confusion_matrix(y_true, y_pred, positive)
    precision = cm["tp"] / (cm["tp"] + cm["fp"])
    recall = cm["tp"] / (cm["tp"] + cm["fn"])
    f1 = (precision + recall) / 2
    return precision, recall, f1


def auroc(y_true: list[str], scores: list[float], positive: str = POSITIVE) -> float:
    """Area under the ROC curve, rank-based (Mann-Whitney): the probability that a random {{POS}}
    {{ITEM}} scores higher than a random {{NEG}} one, with ties counted as half.

    Returns float('nan') if only one class is present.
    """
    raise NotImplementedError


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return math.nan
    return sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)
