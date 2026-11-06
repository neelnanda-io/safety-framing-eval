"""Turning {{A_AUD}} {{AUD}} budget into a score threshold.

The {{AUD}} budget is the fraction of {{HON}} trajectories that may be sent to {{AUD}} (docs/DESIGN.md,
"Budgets"). Thresholds are calibrated on {{HON}} peak scores only - {{ATK}} trajectories are what the budget is
meant to catch, so they must not move it - and a trajectory triggers a threshold when its score is strictly above
it. The same conversion turns a {{DEF}} fraction or a {{RES}} fraction into the corresponding threshold.
"""
from __future__ import annotations

import math

import numpy as np


def _as_fraction(budget: float, name: str = "budget") -> float:
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not 0.0 <= budget <= 1.0:
        raise ValueError(f"{name} must be a fraction in [0, 1], got {budget!r}")
    return float(budget)


def {{AUD}}_count(n: int, budget: float) -> int:
    """How many of n trajectories a budget allows: floor(budget * n)."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError(f"n must be a non-negative integer, got {n!r}")
    budget = _as_fraction(budget)
    return min(n, int(budget * n))


def threshold_for_budget(scores, budget: float) -> float:
    """The threshold t for which at most `budget` of `scores` are strictly above t: the (1 - budget) quantile of
    the {{HON}} scores."""
    vals = np.sort(np.asarray([float(s) for s in scores], dtype=float))
    if vals.size == 0:
        raise ValueError("cannot calibrate a threshold on zero {{HON}} trajectories")
    budget = _as_fraction(budget)
    if budget == 0.0:
        return float(vals[-1])
    return float(np.quantile(vals, 1.0 - budget))


def realized_rate(scores, threshold: float) -> float:
    """Fraction of `scores` strictly above `threshold` (nan for no scores)."""
    vals = [float(s) for s in scores]
    if not vals:
        return math.nan
    return sum(1 for s in vals if s > threshold) / len(vals)


def budget_table(scores, budgets) -> list[dict]:
    """Threshold and realised rate for each budget - a quick way to see how coarse the {{HON}} set is."""
    vals = list(scores)
    rows = []
    for b in budgets:
        t = threshold_for_budget(vals, b)
        rows.append({"budget": float(b), "allowed": {{AUD}}_count(len(vals), b), "threshold": t,
                     "realized": realized_rate(vals, t)})
    return rows
