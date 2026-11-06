"""Smoke tests for the public API."""
import math

from {{PKG}}.budget import threshold_for_budget
from {{PKG}}.data import load_trajectories, split_by_kind
from {{PKG}}.frontier import Point, pareto_front
from {{PKG}}.metrics import {{SAFE}}_from_counts
from {{PKG}}.report import format_pct
from {{PKG}}.scores import aggregate, running_scores
from {{PKG}}.{{PROTOCOLS}} import build


def test_load_sample():
    trajs = load_trajectories("data/trajectories.jsonl")
    {{HON}}_trajs, {{ATK}}_trajs = split_by_kind(trajs)
    assert (len(trajs), len({{HON}}_trajs), len({{ATK}}_trajs)) == (40, 28, 12)
    assert all(t.steps[0].index == 0 for t in trajs)


def test_max_aggregation():
    assert aggregate([1.0, 7.5, 3.0], "max") == 7.5
    assert running_scores([1.0, 7.5, 3.0], "max") == [1.0, 7.5, 7.5]


def test_zero_budget_threshold_is_max():
    assert threshold_for_budget([3.0, 1.0, 2.0], 0.0) == 3.0


def test_simple_front():
    pts = [Point(0.0, 1.0, 0.2), Point(0.1, 0.5, 0.9), Point(0.2, 0.4, 0.1)]
    assert pareto_front(pts) == pts[:2]


def test_counts_ratio():
    assert {{SAFE}}_from_counts(3, 1) == 0.75


def test_format_pct():
    assert format_pct(0.25) == "25.0%"


def test_build_and_decide():
    trajs = load_trajectories("data/trajectories.jsonl")
    {{HON}}_trajs, _ = split_by_kind(trajs)
    p = build({"name": "{{AUD}}_only", "{{AUD}}_budget": 0.1}).fit({{HON}}_trajs)
    assert math.isfinite(p.{{AUD}}_threshold)
    assert {d.action for d in p.decide_all(trajs)} <= {"{{ACC}}", "{{AUD}}", "{{DEF}}"}
