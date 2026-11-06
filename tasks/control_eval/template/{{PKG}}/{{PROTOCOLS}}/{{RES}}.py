"""{{RES_CAP}}: when a trajectory scores high, draw recorded alternates of it and use one that scores low.

Thresholds (both from {{HON}} peak scores): {{AUD}}_threshold from {{AUD}}_budget and {{RES}}_threshold from
{{RES}}_fraction, never above the {{AUD}} threshold. For a trajectory whose running score first exceeds the
{{RES}} threshold at step i0 (docs/DESIGN.md, "{{PROTOCOLS_CAP}}"):

  1. draw up to `max_draws` alternates, uniformly at random with replacement, from
     `traj.alternates`; stop at the first draw whose peak score is at or below the {{RES}} threshold and use it;
  2. if no draw was usable, look at the lowest-scoring sample seen (the original and every draw):
     {{AUD}} if even that one is above the {{AUD}} threshold, otherwise {{DEF}} to the {{TRU}} model.

All interventions happen at step i0. Draws come from a per-trajectory random stream seeded by the {{PROTOCOL}}
seed and the trajectory id, so a trajectory's decision does not depend on which other trajectories are decided,
in what order, or in which Python process.
"""
from __future__ import annotations

import numpy as np

from {{PKG}}.budget import threshold_for_budget
from {{PKG}}.{{PROTOCOLS}}.base import Decision, {{PROTOCOL_CAP}}


class {{RES_CAP}}{{PROTOCOL_CAP}}({{PROTOCOL_CAP}}):
    name = "{{RES}}"

    def __init__(self, {{AUD}}_budget: float = 0.02, {{RES}}_fraction: float = 0.10, max_draws: int = 3,
                 seed: int = 0, method: str = "max", k: int = 3):
        super().__init__({{AUD}}_budget={{AUD}}_budget, method=method, k=k)
        if not 0.0 <= float({{RES}}_fraction) <= 1.0:
            raise ValueError(f"{{RES}}_fraction must be in [0, 1], got {{{RES}}_fraction!r}")
        if int(max_draws) < 0:
            raise ValueError(f"max_draws must be >= 0, got {max_draws!r}")
        self.{{RES}}_fraction = float({{RES}}_fraction)
        self.max_draws = int(max_draws)
        self.seed = int(seed)
        self.{{RES}}_threshold: float | None = None

    def _extra_params(self) -> dict:
        return {"{{RES}}_fraction": self.{{RES}}_fraction, "max_draws": self.max_draws, "seed": self.seed}

    def fit(self, trajectories) -> "{{RES_CAP}}{{PROTOCOL_CAP}}":
        items = self._prepare(trajectories)
        peaks = [self.peak(t) for t in items]
        self.{{AUD}}_threshold = threshold_for_budget(peaks, self.{{AUD}}_budget)
        band = threshold_for_budget(peaks, self.{{RES}}_fraction)
        self.{{RES}}_threshold = min(band, self.{{AUD}}_threshold)
        return self

    def _stream(self, traj) -> np.random.Generator:
        """The random stream for one trajectory's draws."""
        return np.random.default_rng(abs(hash((self.seed, traj.traj_id))))

    def decide(self, traj) -> Decision:
        self._require_fitted()
        i0 = self.crossing(traj, self.{{RES}}_threshold)
        if i0 is None:
            return Decision("{{ACC}}")
        draws = 0
        if traj.alternates and self.max_draws > 0:
            rng = self._stream(traj)
            j = int(rng.integers(len(traj.alternates)))
            for _ in range(self.max_draws):
                draws += 1
                if self.peak(traj.alternates[j]) <= self.{{RES}}_threshold:
                    return Decision("{{ACC}}", step=i0, alternate=j, draws=draws)
        if self.peak(traj) > self.{{AUD}}_threshold:
            return Decision("{{AUD}}", step=i0, draws=draws)
        return Decision("{{DEF}}", step=i0, draws=draws)
