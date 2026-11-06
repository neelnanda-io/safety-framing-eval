"""Markdown build report for the {{TEAM}}: counts per stage, {{RATE_NAME}} per {{GROUP}}, judge health,
near-duplicate clusters and split balance. Written next to the export by `cli build --report`."""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from {{PKG}}.split import SPLITS
from {{PKG}}.stats import ALL


def _pct(x: float) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.1f}%"


def _table(header: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return out


def stage_counts(manifest: dict) -> list[list]:
    c = manifest.get("counts", {})
    return [["read from sources", c.get("n_input", "?")],
            ["unjudgeable (no answered user turn)", c.get("n_unjudgeable", "?")],
            ["exact duplicates removed", c.get("n_duplicates", "?")],
            ["exported", c.get("records", "?")],
            ["near-duplicate clusters", c.get("n_clusters", "?")]]


def judge_health(judgements: dict) -> list[list]:
    statuses = Counter(j.status for j in judgements.values())
    attempts = Counter(j.attempts for j in judgements.values())
    cached = sum(1 for j in judgements.values() if j.from_cache)
    rows = [[f"status {s}", n] for s, n in sorted(statuses.items())]
    rows += [[f"{a} attempt(s)", n] for a, n in sorted(attempts.items())]
    rows.append(["served from cache", cached])
    return rows


def cluster_sizes(cluster_of: dict[str, str]) -> list[list]:
    sizes = Counter(Counter(cluster_of.values()).values())
    return [[size, n] for size, n in sorted(sizes.items())]


def split_balance(records, split_of: dict[str, str]) -> list[list]:
    per_group: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        per_group[r.group][split_of.get(r.record_id, "none")] += 1
    rows = []
    for group in sorted(per_group):
        counts = per_group[group]
        total = sum(counts.values())
        rows.append([group] + [f"{counts.get(s, 0)} ({_pct(counts.get(s, 0) / total)})" for s in SPLITS])
    return rows


def build_report(result, title: str = "{{PROJECT_TITLE}}: build report") -> str:
    """Render a BuildResult (pipeline.build_corpus) as Markdown."""
    lines = [f"# {title}", ""]
    lines += ["## Stages", ""] + _table(["stage", "records"], stage_counts(result.manifest)) + [""]
    rate_rows = [[r.group, r.n, r.k, _pct(r.rate), f"{_pct(r.lo)} - {_pct(r.hi)}", r.n_excluded]
                 for r in result.rates]
    lines += ["## {{RATE_NAME}} per {{GROUP}}", ""]
    lines += _table(["{{GROUP}}", "n", "{{POS}}", "rate", "interval", "excluded"], rate_rows) + [""]
    overall = next((r for r in result.rates if r.group == ALL), None)
    if overall is not None and overall.n_excluded:
        lines += [f"{overall.n_excluded} judgement(s) were excluded from the rates (see DESIGN.md).", ""]
    lines += ["## Judge", ""] + _table(["", "count"], judge_health(result.judgements)) + [""]
    lines += ["## Near-duplicate clusters", ""] + _table(["cluster size", "clusters"], cluster_sizes(result.cluster_of))
    lines += ["", "## Split balance", ""]
    lines += _table(["{{GROUP}}"] + list(SPLITS), split_balance(result.records, result.split_of)) + [""]
    return "\n".join(lines)
