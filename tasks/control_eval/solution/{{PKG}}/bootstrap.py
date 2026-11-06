"""Bootstrap confidence intervals for {{SAFE}} and {{USE}} (docs/DESIGN.md, "Bootstrap").

* Stratified: every replicate redraws the {{HON}} trajectories (n_{{HON}} draws with replacement) and,
  separately, the {{ATK}} trajectories (n_{{ATK}} draws), so each replicate has the same composition as the data.
* Refitted: thresholds are re-calibrated on every replicate's {{HON}} sample, so the intervals include the noise
  of estimating the thresholds from a finite {{HON}} set. The {{PROTOCOLS}} passed in are not modified.
* Paired: all {{PROTOCOLS}} are evaluated on the same replicates, so the interval of a difference between two
  {{PROTOCOLS}} is computed from per-replicate differences.
* Percentile intervals; replicates where a metric is nan are dropped for that metric.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

import numpy as np

from {{PKG}}.data import split_by_kind
from {{PKG}}.metrics import EvalResult, evaluate

METRICS = ("{{SAFE}}", "{{USE}}")


@dataclass
class BootstrapResult:
    point: dict[str, EvalResult]                                   # name -> full-data result
    ci: dict[str, dict[str, tuple[float, float]]]                  # name -> metric -> (lo, hi)
    diff: dict[tuple[str, str], dict[str, tuple[float, float]]]    # (a, b) -> metric -> CI of a - b
    n_boot: int
    seed: int
    level: float
    n_valid: dict[str, dict[str, int]] = field(default_factory=dict)  # name -> metric -> replicates used

    def to_dict(self) -> dict:
        return {
            "point": {k: v.to_dict() for k, v in self.point.items()},
            "ci": {k: {m: list(v) for m, v in d.items()} for k, d in self.ci.items()},
            "diff": {f"{a} - {b}": {m: list(v) for m, v in d.items()} for (a, b), d in self.diff.items()},
            "n_boot": self.n_boot, "seed": self.seed, "level": self.level, "n_valid": self.n_valid,
        }


def replicate_indices(n_{{HON}}: int, n_{{ATK}}: int, n_boot: int, seed: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """`n_boot` pairs (indices into the {{HON}} list, indices into the {{ATK}} list), drawn with replacement."""
    if n_{{HON}} < 1:
        raise ValueError("the bootstrap needs at least one {{HON}} trajectory")
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        h = rng.integers(0, n_{{HON}}, size=n_{{HON}})
        a = rng.integers(0, n_{{ATK}}, size=n_{{ATK}}) if n_{{ATK}} else np.zeros(0, dtype=int)
        out.append((h, a))
    return out


def percentile_ci(values, level: float = 0.95) -> tuple[float, float]:
    """Percentile interval covering `level` of the values; nan values are dropped first. (nan, nan) if none remain."""
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must be in (0, 1), got {level!r}")
    arr = np.asarray([v for v in values if not math.isnan(v)], dtype=float)
    if arr.size == 0:
        return (math.nan, math.nan)
    tail = (1.0 - level) / 2.0
    lo, hi = np.percentile(arr, [100.0 * tail, 100.0 * (1.0 - tail)])
    return (float(lo), float(hi))


def bootstrap({{PROTOCOLS}}: dict, trajectories, n_boot: int = 200, seed: int = 0, level: float = 0.95) -> BootstrapResult:
    """Point estimates and paired, stratified, refitted percentile CIs for every {{PROTOCOL}} in `{{PROTOCOLS}}`."""
    trajectories = list(trajectories)
    {{HON}}_trajs, {{ATK}}_trajs = split_by_kind(trajectories)
    names = list({{PROTOCOLS}})
    point = {name: evaluate(copy.deepcopy(p), trajectories) for name, p in {{PROTOCOLS}}.items()}
    samples = {name: {m: [] for m in METRICS} for name in names}
    for h_idx, a_idx in replicate_indices(len({{HON}}_trajs), len({{ATK}}_trajs), n_boot, seed):
        replicate = [{{HON}}_trajs[i] for i in h_idx] + [{{ATK}}_trajs[i] for i in a_idx]
        for name in names:
            r = evaluate(copy.deepcopy({{PROTOCOLS}}[name]), replicate, refit=True)
            for m in METRICS:
                samples[name][m].append(getattr(r, m))
    ci = {name: {m: percentile_ci(samples[name][m], level) for m in METRICS} for name in names}
    n_valid = {name: {m: sum(not math.isnan(v) for v in samples[name][m]) for m in METRICS} for name in names}
    diff = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            diff[(a, b)] = {m: percentile_ci([x - y for x, y in zip(samples[a][m], samples[b][m])], level)
                            for m in METRICS}
    return BootstrapResult(point=point, ci=ci, diff=diff, n_boot=n_boot, seed=seed, level=level, n_valid=n_valid)
