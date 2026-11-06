"""Aggregate episode results: {{RATE_NAME}}, per-{{STRATEGY_NOUN}} breakdown, turns to success, bootstrap CIs."""
from __future__ import annotations

import math
import random


def success_rate(results) -> float:
    """Fraction of episodes marked {{OUTCOME}}. Errored episodes count as failures: they stay in the
    denominator. Returns nan for an empty list."""
    if not results:
        return math.nan
    return sum(1 for r in results if r.{{OUTCOME}} and r.error is None) / len(results)


def per_strategy(results) -> dict[str, dict]:
    """{strategy: {"n": number of episodes, "rate": success_rate of that strategy's episodes}}, in first-seen order."""
    groups: dict[str, list] = {}
    for r in results:
        groups.setdefault(r.strategy, []).append(r)
    return {s: {"n": len(rs), "rate": success_rate(rs)} for s, rs in groups.items()}


def mean_turns_to_success(results) -> float:
    """Mean turns_used over the episodes marked {{OUTCOME}} (failed and errored ones are excluded).
    Returns nan when no episode succeeded."""
    turns = [r.turns_used for r in results if r.{{OUTCOME}} and r.error is None]
    if not turns:
        return math.nan
    return sum(turns) / len(turns)


def bootstrap_ci(values: list[float], n_boot: int = 1000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for the mean of `values`.

    Draw `n_boot` resamples of len(values) items with replacement using random.Random(seed), take each
    resample's mean, and return the (alpha/2, 1 - alpha/2) percentiles of those means as (lo, hi).
    The same seed always gives the same interval. Returns (nan, nan) for an empty list.
    """
    if n_boot < 1:
        raise ValueError(f"n_boot must be at least 1, got {n_boot}")
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    if not values:
        return math.nan, math.nan
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(n_boot))
    lo_i = min(n_boot - 1, max(0, int(math.floor(alpha / 2 * n_boot))))
    hi_i = min(n_boot - 1, max(0, int(math.ceil((1 - alpha / 2) * n_boot)) - 1))
    return means[lo_i], means[hi_i]
