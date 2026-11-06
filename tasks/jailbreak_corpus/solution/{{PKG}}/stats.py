"""{{RATE_NAME}} per {{GROUP}} with confidence intervals, a bootstrap CI and inter-judge agreement
(docs/DESIGN.md, "Statistics")."""
from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from statistics import NormalDist

from {{PKG}} import POSITIVE
from {{PKG}}.judge import Judgement
from {{PKG}}.records import Record

ALL = "ALL"


@dataclass(frozen=True)
class RateRow:
    group: str
    n: int  # judgements counted
    k: int  # of which {{POS}}
    rate: float
    lo: float
    hi: float
    n_excluded: int  # judgements left out (see DESIGN.md)


def z_for(confidence: float) -> float:
    """Critical value of the standard normal for an interval with the given coverage."""
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    return NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)


def wilson_interval(k: int, n: int, z: float) -> tuple[float, float]:
    """Wilson score interval for k successes out of n."""
    if k < 0 or k > n:
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def rate_table(records: list[Record], judgements: dict[str, Judgement],
               confidence: float = 0.95) -> list[RateRow]:
    """One row per {{GROUP}} (sorted by name), then an "ALL" row over every {{GROUP}}."""
    z = z_for(confidence)
    by_group: dict[str, list[Judgement]] = defaultdict(list)
    missing: dict[str, int] = defaultdict(int)
    for r in records:
        j = judgements.get(r.record_id)
        if j is None:
            missing[r.group] += 1
            continue
        by_group[r.group].append(j)

    rows = []
    for group in sorted(set(by_group) | set(missing)):
        js = by_group.get(group, [])
        ok = [j for j in js if j.status == "ok"]
        n = len(ok)
        k = sum(1 for j in ok if j.verdict == POSITIVE)
        lo, hi = wilson_interval(k, n, z)
        rows.append(RateRow(group, n, k, k / n if n else math.nan, lo, hi, missing.get(group, 0) + len(js) - n))

    n_all = sum(row.n for row in rows)
    k_all = sum(row.k for row in rows)
    rate_all = k_all / n_all if n_all else math.nan
    lo, hi = wilson_interval(k_all, n_all, z)
    rows.append(RateRow(ALL, n_all, k_all, rate_all, lo, hi, sum(row.n_excluded for row in rows)))
    return rows


def bootstrap_rate_ci(outcomes: list[int], n_boot: int = 1000, confidence: float = 0.95,
                      seed: int = 0) -> tuple[float, float]:
    """Percentile-bootstrap interval for the mean of 0/1 outcomes (see DESIGN.md)."""
    if not outcomes:
        raise ValueError("bootstrap_rate_ci needs at least one outcome")
    rng = random.Random(seed)
    n = len(outcomes)
    means = sorted(sum(rng.choices(outcomes, k=n)) / n for _ in range(n_boot))
    alpha = (1.0 - confidence) / 2.0

    def quantile(q: float) -> float:
        pos = q * (len(means) - 1)
        lo_i = math.floor(pos)
        hi_i = min(lo_i + 1, len(means) - 1)
        return means[lo_i] + (means[hi_i] - means[lo_i]) * (pos - lo_i)

    return quantile(alpha), quantile(1.0 - alpha)


def cohen_kappa(judgements_a: list[Judgement], judgements_b: list[Judgement]) -> float:
    """Cohen's kappa between two judges' verdicts on the same records."""
    ok_b = {j.record_id: j for j in judgements_b if j.status == "ok"}
    pairs = [(a.verdict, ok_b[a.record_id].verdict) for a in judgements_a
             if a.status == "ok" and a.record_id in ok_b]
    if not pairs:
        return math.nan
    n = len(pairs)
    p_observed = sum(1 for a, b in pairs if a == b) / n
    labels = sorted({v for pair in pairs for v in pair})
    p_expected = sum((sum(1 for a, _ in pairs if a == label) / n) * (sum(1 for _, b in pairs if b == label) / n)
                     for label in labels)
    if p_expected >= 1.0:
        return 1.0
    return (p_observed - p_expected) / (1.0 - p_expected)


def format_rate_table(rows: list[RateRow]) -> str:
    """Fixed-width text table; rates and bounds as percentages."""
    width = max([len("{{GROUP}}")] + [len(r.group) for r in rows])
    out = [f"{'{{GROUP}}':<{width}}  {'n':>5}  {'k':>5}  {'rate':>7}  {'interval':>17}  {'excl':>5}"]
    for r in rows:
        rate = "    n/a" if math.isnan(r.rate) else f"{r.rate * 100:6.1f}%"
        out.append(f"{r.group:<{width}}  {r.n:>5}  {r.k:>5}  {rate}  [{r.lo * 100:5.1f}%, {r.hi * 100:5.1f}%]"
                   f"  {r.n_excluded:>5}")
    return "\n".join(out)
