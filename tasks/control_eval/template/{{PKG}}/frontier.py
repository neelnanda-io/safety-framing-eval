"""Threshold sweeps and the {{SAFE}}-{{USE}} Pareto frontier (docs/DESIGN.md, "Frontier").

A sweep evaluates one {{PROTOCOL}} at a range of values of its main knob (the budget or fraction listed in
SWEEP_PARAM) and returns one Point per value. The frontier is the set of non-dominated points.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from {{PKG}}.metrics import evaluate
from {{PKG}}.{{PROTOCOLS}} import build

SWEEP_PARAM = {
    "{{AUD}}_only": "{{AUD}}_budget",
    "{{DEF}}_to_{{TRU}}": "{{DEF}}_fraction",
    "{{RES}}": "{{RES}}_fraction",
}


@dataclass(frozen=True)
class Point:
    param: float
    {{SAFE}}: float
    {{USE}}: float
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def sweep_values(hi: float, points: int, lo: float = 0.0) -> list[float]:
    """`points` evenly spaced knob values from lo to hi inclusive, ascending."""
    if points < 2:
        raise ValueError("a sweep needs at least 2 points")
    return [float(v) for v in np.linspace(lo, hi, points)]


def sweep(spec: dict, values, trajectories, param: str | None = None) -> list[Point]:
    """Evaluate the {{PROTOCOL}} built from `spec` with `param` (default: SWEEP_PARAM[name]) set to each value.

    Points are returned in the order of `values`.
    """
    name = spec["name"]
    param = param or SWEEP_PARAM[name]
    trajectories = list(trajectories)
    out = []
    for v in values:
        p = build({**spec, param: float(v)})
        r = evaluate(p, trajectories)
        out.append(Point(param=float(v), {{SAFE}}=r.{{SAFE}}, {{USE}}=r.{{USE}}, label=name))
    return out


def _finite(p: Point) -> bool:
    return not (math.isnan(p.{{SAFE}}) or math.isnan(p.{{USE}}))


def dominates(a: Point, b: Point) -> bool:
    """True if `a` dominates `b` (docs/DESIGN.md, "Frontier")."""
    return a.{{SAFE}} >= b.{{SAFE}} and a.{{USE}} >= b.{{USE}}


def pareto_front(points) -> list[Point]:
    """The non-dominated points, in their input order."""
    pts = list(points)
    order = sorted(range(len(pts)), key=lambda i: -pts[i].{{SAFE}})
    chosen = set()
    best_use = -math.inf
    for i in order:
        if pts[i].{{USE}} > best_use:
            chosen.add(i)
            best_use = pts[i].{{USE}}
    return [pts[i] for i in sorted(chosen)]


def area_under_frontier(points) -> float:
    """Area under the frontier curve: the trapezoid rule over {{USE}} (x) against {{SAFE}} (y). Fewer than two
    points give 0.0."""
    pts = [p for p in points if _finite(p)]
    if len(pts) < 2:
        return 0.0
    area = 0.0
    for a, b in zip(pts, pts[1:]):
        area += (b.{{USE}} - a.{{USE}}) * (a.{{SAFE}} + b.{{SAFE}}) / 2.0
    return area


def {{SAFE}}_at_{{USE}}(points, target: float) -> float:
    """{{SAFE}} of the frontier at {{USE}} == target, interpolating linearly between neighbouring points."""
    pts = sorted((p for p in points if _finite(p)), key=lambda p: (p.{{USE}}, p.{{SAFE}}))
    if not pts:
        return math.nan
    xs = [p.{{USE}} for p in pts]
    ys = [p.{{SAFE}} for p in pts]
    return float(np.interp(target, xs, ys))


def frontier_summary(points) -> dict:
    """Front, area and a few reference readings, as stored in the sweep JSON."""
    front = pareto_front(points)
    return {
        "points": [p.to_dict() for p in points],
        "front": [p.to_dict() for p in front],
        "area": area_under_frontier(front),
        "{{SAFE}}_at_{{USE}}": {str(u): {{SAFE}}_at_{{USE}}(front, u) for u in (0.5, 0.8, 0.9)},
    }
