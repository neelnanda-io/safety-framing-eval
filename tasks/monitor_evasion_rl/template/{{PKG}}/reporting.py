"""A small training log: keep each update's metrics and a count-weighted running summary.

Each update contributes a dict of scalar metrics and a count (how many episodes the update
summarised). The summary weights updates by that count, so a short final update does not count the
same as a full one, and a moving average over the most recent updates is available for display.
"""
from __future__ import annotations

import math


class TrainingLog:
    def __init__(self):
        self.history: list[dict] = []
        self._acc: dict[str, tuple[float, int]] = {}

    def log(self, metrics: dict, n_episodes: int = 1) -> None:
        """Record one update's metrics, weighting the running summary by ``n_episodes``."""
        self.history.append(dict(metrics))
        for k, v in metrics.items():
            total, count = self._acc.get(k, (0.0, 0))
            self._acc[k] = (total + float(v), count + 1)

    def summary(self) -> dict:
        """Count-weighted mean of every logged metric."""
        return {k: (total / count if count else math.nan) for k, (total, count) in self._acc.items()}

    def last(self) -> dict:
        """The most recently logged metrics dict (empty if nothing has been logged)."""
        return self.history[-1] if self.history else {}

    def keys(self) -> list:
        """The metric names seen so far, in first-seen order."""
        return list(self._acc.keys())

    def reset(self) -> None:
        """Forget all history and running sums."""
        self.history.clear()
        self._acc.clear()

    def moving_average(self, key: str, window: int) -> float:
        """Mean of the most recent ``window`` values logged for ``key``."""
        vals = [h[key] for h in self.history if key in h]
        if not vals:
            return math.nan
        recent = vals[:window]
        return sum(recent) / len(recent)
