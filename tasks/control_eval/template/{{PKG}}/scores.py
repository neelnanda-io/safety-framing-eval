"""Aggregating per-step {{SUSP}} scores into trajectory-level scores.

A {{PROTOCOL}} watches a trajectory step by step. After step i it knows the *running score*
r_i = aggregate(x_0, ..., x_i) of {{MON_DESC}}'s per-step scores x, and it intervenes at the first step whose
running score crosses its threshold. The *peak score* of a trajectory is max_i r_i: a trajectory
reaches threshold t at some step exactly when its peak score is above t, which is why thresholds are
calibrated on peak scores. See docs/DESIGN.md, section "Scores".
"""
from __future__ import annotations

import heapq
import math

METHODS = ("max", "mean", "topk")


def _validate(method: str, k: int) -> None:
    if method == "topk" and (isinstance(k, bool) or not isinstance(k, int) or k < 1):
        raise ValueError(f"topk needs an integer k >= 1, got {k!r}")


def aggregate(values, method: str = "max", k: int = 3) -> float:
    """Aggregate a sequence of per-step scores into one number.

    max: the largest value. mean: the arithmetic mean. topk: the mean of the k largest values.
    A trajectory with no steps scores 0.0 under every method.
    """
    _validate(method, k)
    vals = [float(v) for v in values]
    if method == "max":
        return max(vals)
    if method == "mean":
        return sum(vals) / len(vals)
    return sum(sorted(vals, reverse=True)[:k]) / k


def running_scores(values, method: str = "max", k: int = 3) -> list[float]:
    """[r_0, r_1, ...] with r_i = aggregate(values[: i + 1], method, k), computed in one pass."""
    _validate(method, k)
    out: list[float] = []
    if method == "max":
        best = -math.inf
        for x in values:
            best = max(best, float(x))
            out.append(best)
    elif method == "mean":
        m = 0.0
        for i, x in enumerate(values):
            m += (float(x) - m) / max(i, 1)
            out.append(m)
    else:
        top: list[float] = []  # min-heap holding the k largest values seen so far
        total = 0.0
        for x in values:
            x = float(x)
            if len(top) < k:
                heapq.heappush(top, x)
                total += x
            elif x > top[0]:
                total += x - heapq.heapreplace(top, x)
            out.append(total / len(top))
    return out


class ScoreCache:
    """Memoised running scores.

    The sweep evaluates the same trajectories under many thresholds and the {{RES}} {{PROTOCOL}} scores
    alternates repeatedly, so running scores are computed once per (trajectory key, method, k). Keys are
    trajectory / alternate ids, which are unique within a dataset; {{PROTOCOLS}} start a fresh cache in fit().
    """

    def __init__(self):
        self._data: dict[tuple, list[float]] = {}
        self.hits = 0
        self.misses = 0

    def running(self, key: str, values, method: str, k: int) -> list[float]:
        cache_key = (key, method)
        found = self._data.get(cache_key)
        if found is not None:
            self.hits += 1
            return found
        self.misses += 1
        found = running_scores(values, method, k)
        self._data[cache_key] = found
        return found

    def __len__(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        self._data.clear()
        self.hits = self.misses = 0


def _running(item, method: str, k: int, cache: ScoreCache | None) -> list[float]:
    """Running scores of a Trajectory or an Alternate (anything with .key and .scores)."""
    if cache is None:
        return running_scores(item.scores, method, k)
    return cache.running(item.key, item.scores, method, k)


def final_score(item, method: str = "max", k: int = 3, cache: ScoreCache | None = None) -> float:
    """The aggregate over the whole trajectory (r_last); 0.0 for a trajectory without steps."""
    return _running(item, method, k, cache)[-1]


def peak_score(item, method: str = "max", k: int = 3, cache: ScoreCache | None = None) -> float:
    """max_i r_i; 0.0 for a trajectory without steps. Equal to final_score for method="max"."""
    return max(_running(item, method, k, cache))


def first_crossing(item, threshold: float, method: str = "max", k: int = 3,
                   cache: ScoreCache | None = None) -> int | None:
    """The first (0-based) step whose running score reaches `threshold`, or None if there is none."""
    for i, r in enumerate(_running(item, method, k, cache)):
        if r >= threshold:
            return i
    return None


def score_table(trajectories, method: str = "max", k: int = 3) -> list[dict]:
    """Per-trajectory score summary (used by the `scores` CLI command and handy in notebooks)."""
    rows = []
    for t in trajectories:
        r = running_scores(t.scores, method, k)
        rows.append({"id": t.traj_id, "kind": t.kind, "n_steps": len(r), "final": r[-1] if r else 0.0,
                     "peak": max(r) if r else 0.0,
                     "peak_step": (max(range(len(r)), key=lambda i: (r[i], -i)) if r else None)})
    return rows
