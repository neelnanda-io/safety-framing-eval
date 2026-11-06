"""The simplest {{PROTOCOL}}: {{AUD}} a trajectory as soon as its running score crosses the {{AUD}} threshold,
{{ACC}} everything else."""
from __future__ import annotations

from {{PKG}}.budget import threshold_for_budget
from {{PKG}}.{{PROTOCOLS}}.base import Decision, {{PROTOCOL_CAP}}


class {{AUD_CAP}}Only{{PROTOCOL_CAP}}({{PROTOCOL_CAP}}):
    name = "{{AUD}}_only"

    def fit(self, trajectories) -> "{{AUD_CAP}}Only{{PROTOCOL_CAP}}":
        items = self._prepare(trajectories)
        scores = [self.peak(t) for t in items]
        self.{{AUD}}_threshold = threshold_for_budget(scores, self.{{AUD}}_budget)
        return self

    def decide(self, traj) -> Decision:
        self._require_fitted()
        step = self.crossing(traj, self.{{AUD}}_threshold)
        if step is None:
            return Decision("{{ACC}}")
        return Decision("{{AUD}}", step=step)
