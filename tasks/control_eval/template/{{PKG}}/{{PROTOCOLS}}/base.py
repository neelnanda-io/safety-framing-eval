"""Shared machinery for {{PROTOCOLS}}.

A {{PROTOCOL}} is fitted on the {{HON}} trajectories of a dataset (this sets its thresholds from its budgets) and
then decides, for every trajectory, what happens to the {{UNT}} model's work: "{{ACC}}" it, send it to "{{AUD}}"
({{AUD_DESC}}), or "{{DEF}}" to the {{TRU}} model, which redoes the task. See docs/DESIGN.md, "{{PROTOCOLS_CAP}}".
"""
from __future__ import annotations

from dataclasses import dataclass

from {{PKG}}.scores import METHODS, ScoreCache, final_score, first_crossing, peak_score, running_scores

ACTIONS = ("{{ACC}}", "{{AUD}}", "{{DEF}}")


@dataclass(frozen=True)
class Decision:
    """What a {{PROTOCOL}} did with one trajectory.

    step:      0-based step at which the {{PROTOCOL}} intervened ({{AUD}}, {{DEF}} or {{RES}}); None if it never did.
    alternate: index into `traj.alternates` of the {{RES}} that was finally used, if any.
    draws:     how many {{RES}} draws were made.
    """
    action: str
    step: int | None = None
    alternate: int | None = None
    draws: int = 0

    def __post_init__(self):
        if self.action not in ACTIONS:
            raise ValueError(f"unknown action {self.action!r}; expected one of {ACTIONS}")
        if self.step is not None and self.step < 0:
            raise ValueError(f"step must be >= 0, got {self.step}")


class {{PROTOCOL_CAP}}:
    """Base class. Subclasses set `name`, implement fit() and decide(), and list extra parameters in
    `_extra_params()`."""

    name = "base"

    def __init__(self, {{AUD}}_budget: float = 0.02, method: str = "max", k: int = 3):
        if method not in METHODS:
            raise ValueError(f"unknown aggregation method {method!r}; expected one of {METHODS}")
        if not 0.0 <= float({{AUD}}_budget) <= 1.0:
            raise ValueError(f"{{AUD}}_budget must be in [0, 1], got {{{AUD}}_budget!r}")
        self.{{AUD}}_budget = float({{AUD}}_budget)
        self.method = method
        self.k = int(k)
        self.{{AUD}}_threshold: float | None = None
        self.cache = ScoreCache()

    # ---- parameters ----------------------------------------------------------------------------------------
    def _extra_params(self) -> dict:
        return {}

    def params(self) -> dict:
        """Everything that determines this {{PROTOCOL}}'s decisions (used in reports and cache keys)."""
        out = {"name": self.name, "{{AUD}}_budget": self.{{AUD}}_budget, "method": self.method, "k": self.k}
        out.update(self._extra_params())
        return out

    def describe(self) -> str:
        inner = ", ".join(f"{k}={v}" for k, v in self.params().items() if k != "name")
        return f"{self.name}({inner})"

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.describe()}>"

    # ---- scoring helpers -----------------------------------------------------------------------------------
    def running(self, item) -> list[float]:
        return self.cache.running(item.key, item.scores, self.method, self.k)

    def peak(self, item) -> float:
        return peak_score(item, self.method, self.k, cache=self.cache)

    def final(self, item) -> float:
        return final_score(item, self.method, self.k, cache=self.cache)

    def crossing(self, item, threshold: float) -> int | None:
        return first_crossing(item, threshold, self.method, self.k, cache=self.cache)

    # ---- fitting / deciding --------------------------------------------------------------------------------
    def _prepare(self, trajectories) -> list:
        """Common start of fit(): materialise the {{HON}} trajectories and start a fresh score cache."""
        items = list(trajectories)
        if not items:
            raise ValueError(f"{self.name}: fit() needs at least one {{HON}} trajectory")
        self.cache = ScoreCache()
        return items

    def fit(self, trajectories) -> "{{PROTOCOL_CAP}}":
        """Calibrate thresholds on the given {{HON}} trajectories; returns self."""
        raise NotImplementedError

    def is_fitted(self) -> bool:
        return self.{{AUD}}_threshold is not None

    def _require_fitted(self) -> None:
        if not self.is_fitted():
            raise RuntimeError(f"{self.name}: call fit() before decide()")

    def decide(self, traj) -> Decision:
        raise NotImplementedError

    def decide_all(self, trajectories) -> list[Decision]:
        return [self.decide(t) for t in trajectories]


def unscored_running(item, method: str = "max", k: int = 3) -> list[float]:
    """Running scores without a cache (for debugging a single trajectory)."""
    return running_scores(item.scores, method, k)
