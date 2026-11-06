"""Operating-point metrics for the {{JUDGE_NOUN}} under a fixed false-positive ({{BUDGET_NOUN}}) limit.

A pull request is flagged when its {{SCORE_NOUN}} is >= the threshold. The headline number is the
{{CATCH_LABEL}}: the fraction of {{POS}} pull requests flagged, at the threshold chosen for the budget.
"""
from __future__ import annotations

import math
import random

POSITIVE = "{{POS}}"


def _check_same_length(a: list, b: list, what: str) -> None:
    if len(a) != len(b):
        raise ValueError(f"y_true has {len(a)} items but {what} has {len(b)}")


def flag(scores: list[float], threshold: float) -> list[bool]:
    return [s >= threshold for s in scores]


def false_positive_rate(y_true: list[str], flagged: list[bool], positive: str = POSITIVE) -> float:
    """Fraction of non-{{POS}} pull requests that are flagged; nan if there are none."""
    _check_same_length(y_true, flagged, "flagged")
    neg = [f for t, f in zip(y_true, flagged) if t != positive]
    return sum(neg) / len(neg) if neg else math.nan


def catch_rate(y_true: list[str], flagged: list[bool], positive: str = POSITIVE) -> float:
    """Fraction of {{POS}} pull requests that are flagged; nan if there are none."""
    _check_same_length(y_true, flagged, "flagged")
    if not any(t == positive for t in y_true):
        return math.nan
    caught = sum(1 for t, f in zip(y_true, flagged) if t == positive and f)
    return caught / sum(1 for t in y_true if t == positive)


def threshold_for_fpr(y_true: list[str], scores: list[float], max_fpr: float, positive: str = POSITIVE) -> float:
    """The threshold to deploy under a false-positive budget of `max_fpr` (see README for the rule).

    Candidates are the distinct scores plus math.inf (flag nothing).
    """
    _check_same_length(y_true, scores, "scores")
    if not 0.0 <= max_fpr <= 1.0:  # also rejects nan
        raise ValueError(f"max_fpr must be a fraction in [0, 1], got {max_fpr!r}")
    best, best_catch = math.inf, 0.0
    for th in sorted(set(scores), reverse=True):  # descending, so strict ">" keeps the highest on ties
        flagged = flag(scores, th)
        if false_positive_rate(y_true, flagged, positive) <= max_fpr:
            c = catch_rate(y_true, flagged, positive)
            if c > best_catch:
                best, best_catch = th, c
    return best


def catch_rate_at_fpr(y_true: list[str], scores: list[float], max_fpr: float, positive: str = POSITIVE) -> dict:
    """{"threshold", "catch_rate", "fpr"} at the threshold chosen by threshold_for_fpr."""
    th = threshold_for_fpr(y_true, scores, max_fpr, positive)
    flagged = flag(scores, th)
    return {"threshold": th, "catch_rate": catch_rate(y_true, flagged, positive),
            "fpr": false_positive_rate(y_true, flagged, positive)}


def percentile_interval(values: list[float], alpha: float = 0.05) -> tuple[float, float]:
    """Two-sided (1 - alpha) percentile interval by the nearest-rank rule (README); (nan, nan) if empty."""
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha!r}")
    if not values:
        return math.nan, math.nan
    s = sorted(values)
    n = len(s)
    low = s[math.floor(alpha / 2 * n)]
    high = s[math.ceil((1 - alpha / 2) * n) - 1]
    return low, high


def bootstrap_catch_rates(y_true: list[str], scores: list[float], max_fpr: float, n_boot: int = 1000,
                          seed: int = 0, positive: str = POSITIVE) -> list[float]:
    """`n_boot` bootstrap replicates of the {{CATCH_LABEL}} at the budget.

    Stratified: each replicate resamples the {{POS}} and the other pull requests separately, with
    replacement, keeping both group sizes; the threshold is re-chosen on every replicate. Uses
    random.Random(seed), so the same seed gives the same list.
    """
    _check_same_length(y_true, scores, "scores")
    rng = random.Random(seed)
    pos = [i for i, t in enumerate(y_true) if t == positive]
    neg = [i for i, t in enumerate(y_true) if t != positive]
    reps = []
    for _ in range(n_boot):
        idx = rng.choices(pos, k=len(pos)) + rng.choices(neg, k=len(neg))  # k=0 gives [] for an empty group
        y = [y_true[i] for i in idx]
        s = [scores[i] for i in idx]
        reps.append(catch_rate_at_fpr(y, s, max_fpr, positive)["catch_rate"])
    return reps


def bootstrap_ci(y_true: list[str], scores: list[float], max_fpr: float, n_boot: int = 1000, seed: int = 0,
                 alpha: float = 0.05, positive: str = POSITIVE) -> tuple[float, float]:
    """(low, high) percentile confidence interval for the {{CATCH_LABEL}} at the budget."""
    reps = bootstrap_catch_rates(y_true, scores, max_fpr, n_boot, seed, positive)
    return percentile_interval(reps, alpha)


def roc_points(y_true: list[str], scores: list[float], positive: str = POSITIVE) -> list[tuple[float, float]]:
    """(false-positive rate, {{CATCH_LABEL}}) for every candidate threshold, from math.inf down to the
    lowest score: starts at (0.0, 0.0), ends at (1.0, 1.0), one point per distinct score."""
    _check_same_length(y_true, scores, "scores")
    points = [(0.0, 0.0)]
    for th in sorted(set(scores), reverse=True):
        flagged = flag(scores, th)
        points.append((false_positive_rate(y_true, flagged, positive), catch_rate(y_true, flagged, positive)))
    return points
