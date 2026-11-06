"""{{DEF_CAP}} to {{TRU}}: {{AUD}} the highest-scoring trajectories, hand the next band to the {{TRU}} model.

Two thresholds, both calibrated on {{HON}} peak scores (docs/DESIGN.md, "{{PROTOCOLS_CAP}}"):
  {{AUD}}_threshold  from {{AUD}}_budget,
  {{DEF}}_threshold  from {{DEF}}_fraction (the fraction of {{HON}} trajectories the {{PROTOCOL}} intervenes on at
                    all), never above the {{AUD}} threshold.
The {{PROTOCOL}} acts at the first step whose running score is above the {{DEF}} threshold: {{AUD}} if the
running score is above the {{AUD}} threshold, otherwise {{DEF}}.
"""
from __future__ import annotations

from {{PKG}}.budget import threshold_for_budget
from {{PKG}}.{{PROTOCOLS}}.base import Decision, {{PROTOCOL_CAP}}


class {{DEF_CAP}}{{PROTOCOL_CAP}}({{PROTOCOL_CAP}}):
    name = "{{DEF}}_to_{{TRU}}"

    def __init__(self, {{AUD}}_budget: float = 0.02, {{DEF}}_fraction: float = 0.10, method: str = "max",
                 k: int = 3):
        super().__init__({{AUD}}_budget={{AUD}}_budget, method=method, k=k)
        if not 0.0 <= float({{DEF}}_fraction) <= 1.0:
            raise ValueError(f"{{DEF}}_fraction must be in [0, 1], got {{{DEF}}_fraction!r}")
        self.{{DEF}}_fraction = float({{DEF}}_fraction)
        self.{{DEF}}_threshold: float | None = None

    def _extra_params(self) -> dict:
        return {"{{DEF}}_fraction": self.{{DEF}}_fraction}

    def fit(self, trajectories) -> "{{DEF_CAP}}{{PROTOCOL_CAP}}":
        items = self._prepare(trajectories)
        peaks = [self.peak(t) for t in items]
        self.{{AUD}}_threshold = threshold_for_budget(peaks, self.{{AUD}}_budget)
        self.{{DEF}}_threshold = threshold_for_budget(peaks, self.{{DEF}}_fraction)
        return self

    def decide(self, traj) -> Decision:
        self._require_fitted()
        step = self.crossing(traj, self.{{AUD}}_threshold)
        if step is not None:
            return Decision("{{AUD}}", step=step)
        step = self.crossing(traj, self.{{DEF}}_threshold)
        if step is not None:
            return Decision("{{DEF}}", step=step)
        return Decision("{{ACC}}")
