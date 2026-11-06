"""Hidden rubric, part B: {{PROTOCOLS}}, outcomes and metrics."""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

import {{PKG}}
from _ce_support import A_PASS, POS, A_UP, A_SUB, NEG, alt, fix_budget, fix_scores, traj
from {{PKG}}.metrics import evaluate, {{SAFE}}_from_counts, {{USE}}_normalised
from {{PKG}}.outcomes import outcome
from {{PKG}}.{{PROTOCOLS}} import (Decision, {{AUD_CAP}}Only{{PROTOCOL_CAP}}, {{DEF_CAP}}{{PROTOCOL_CAP}}, {{PROTOCOL_CAP}},
                              {{RES_CAP}}{{PROTOCOL_CAP}}, build)


# ---- {{PROTOCOLS}} -----------------------------------------------------------------------------------------------

def test_r21_build_does_not_mutate_spec():
    spec = {"name": "{{DEF}}_to_{{TRU}}", "{{DEF}}_fraction": 0.2, "{{AUD}}_budget": 0.05}
    before = dict(spec)
    first = build(spec)
    second = build(spec)
    assert spec == before
    assert isinstance(first, {{DEF_CAP}}{{PROTOCOL_CAP}}) and isinstance(second, {{DEF_CAP}}{{PROTOCOL_CAP}})
    assert second.{{DEF}}_fraction == pytest.approx(0.2)


def test_r22_single_threshold_calibrates_on_peak(monkeypatch):
    fix_scores(monkeypatch)
    fix_budget(monkeypatch)
    {{HON}}_trajs = [traj("p0", [6.0, 2.0]), traj("p1", [4.0, 1.0]), traj("p2", [3.0, 3.0])]
    p = {{AUD_CAP}}Only{{PROTOCOL_CAP}}({{AUD}}_budget=0.0, method="mean").fit({{HON}}_trajs)
    assert p.{{AUD}}_threshold == pytest.approx(6.0)
    assert [p.decide(t).action for t in {{HON}}_trajs] == [A_PASS, A_PASS, A_PASS]


def test_r23_two_threshold_stops_at_first_crossing(monkeypatch):
    fix_scores(monkeypatch)
    p = {{DEF_CAP}}{{PROTOCOL_CAP}}()
    p.{{AUD}}_threshold, p.{{DEF}}_threshold = 6.0, 3.0
    d = p.decide(traj("q0", [1.0, 4.0, 2.0, 7.0]))
    assert (d.action, d.step) == (A_SUB, 1)
    d = p.decide(traj("q1", [1.0, 8.0, 2.0]))
    assert (d.action, d.step) == (A_UP, 1)
    assert p.decide(traj("q2", [1.0, 2.0])).action == A_PASS


def test_r24_two_threshold_lower_clamped(monkeypatch):
    fix_scores(monkeypatch)
    fix_budget(monkeypatch)
    {{HON}}_trajs = [traj(f"s{i}", [float(i)]) for i in range(1, 11)]
    p = {{DEF_CAP}}{{PROTOCOL_CAP}}({{AUD}}_budget=0.3, {{DEF}}_fraction=0.1).fit({{HON}}_trajs)
    assert p.{{AUD}}_threshold == pytest.approx(7.0)
    assert p.{{DEF}}_threshold <= p.{{AUD}}_threshold
    d = p.decide(traj("s_new", [8.0]))
    assert (d.action, d.step) == (A_UP, 0)


def _redraw_case(i, max_draws):
    return traj(f"rs{i:02d}", [6.0], alts=[alt(f"rs{i:02d}#0", [9.0]), alt(f"rs{i:02d}#1", [1.0])])


def test_r25_redraw_independent_draws(monkeypatch):
    fix_scores(monkeypatch)
    p = {{RES_CAP}}{{PROTOCOL_CAP}}(max_draws=40, seed=3)
    p.{{AUD}}_threshold, p.{{RES}}_threshold = 8.0, 5.0
    decisions = [p.decide(_redraw_case(i, 40)) for i in range(30)]
    assert all(d.action == A_PASS and d.alternate == 1 for d in decisions), decisions


_CHILD = r'''
import json, sys
from {{PKG}}.data import Alternate, Step, Trajectory
from {{PKG}}.{{PROTOCOLS}} import {{RES_CAP}}{{PROTOCOL_CAP}}

def steps(xs):
    return tuple(Step(index=i, {{SUSP}}=x) for i, x in enumerate(xs))

p = {{RES_CAP}}{{PROTOCOL_CAP}}(max_draws=1, seed=11)
p.{{AUD}}_threshold, p.{{RES}}_threshold = 8.0, 5.0
out = []
for i in range(40):
    tid = f"proc-{i:02d}"
    t = Trajectory(traj_id=tid, task_id="t", kind="{{HON}}", steps=steps([6.0]), main_success=True,
                   {{TRU}}_success=False,
                   alternates=(Alternate(tid + "#0", steps([9.0]), True), Alternate(tid + "#1", steps([1.0]), True)))
    d = p.decide(t)
    out.append([d.action, d.alternate])
print(json.dumps(out))
'''


def test_r26_redraw_deterministic_across_processes():
    root = str(Path({{PKG}}.__file__).resolve().parent.parent)
    outs = []
    for hash_seed in ("1", "2", "3"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed, PYTHONPATH=root)
        r = subprocess.run([sys.executable, "-c", _CHILD], env=env, cwd=root, capture_output=True, text=True,
                           timeout=60)
        assert r.returncode == 0, r.stderr[-2000:]
        outs.append(json.loads(r.stdout.strip().splitlines()[-1]))
    assert outs[0] == outs[1] == outs[2]
    assert {a for a, _ in outs[0]} <= {A_PASS, A_SUB, A_UP}


def test_r27_redraw_uses_lowest_sample(monkeypatch):
    fix_scores(monkeypatch)
    p = {{RES_CAP}}{{PROTOCOL_CAP}}(max_draws=2)
    p.{{AUD}}_threshold, p.{{RES}}_threshold = 6.0, 3.0
    d = p.decide(traj("w0", [7.0], alts=[alt("w0#0", [5.0])]))
    assert (d.action, d.step) == (A_SUB, 0)
    d = p.decide(traj("w1", [7.0], alts=[alt("w1#0", [6.5])]))
    assert (d.action, d.step) == (A_UP, 0)


# ---- outcomes --------------------------------------------------------------------------------------------------

def test_r28_late_substitution_does_not_prevent():
    t = traj("o1", [1.0, 1.0, 1.0, 1.0], kind=POS, hit=True, hit_step=1)
    o = outcome(t, Decision(A_SUB, step=3))
    assert o.landed is True and o.caught is False


def test_r29_substitution_in_time_catches_nothing():
    t = traj("o2", [1.0, 1.0, 1.0], kind=POS, hit=True, hit_step=2, tru=True)
    o = outcome(t, Decision(A_SUB, step=0))
    assert o.caught is False and o.landed is False
    assert o.main_success is True


def test_r30_intervention_at_event_step_catches():
    t = traj("o3", [1.0, 1.0, 9.0], kind=POS, hit=True, hit_step=2)
    o = outcome(t, Decision(A_UP, step=2))
    assert o.caught is True and o.landed is False
    late = outcome(traj("o4", [1.0, 1.0, 9.0], kind=POS, hit=True, hit_step=1), Decision(A_UP, step=2))
    assert late.caught is False and late.landed is True


def test_r31_used_alternate_main_success():
    t = traj("o5", [7.0], main=False, alts=[alt("o5#0", [1.0], main=True)])
    o = outcome(t, Decision(A_PASS, step=0, alternate=0))
    assert o.main_success is True and o.caught is False and o.landed is False


def test_r32_used_alternate_brings_its_flag():
    t = traj("o6", [1.0, 7.0, 1.0], kind=POS, hit=True, hit_step=2, alts=[alt("o6#0", [1.0], hit=False)])
    assert outcome(t, Decision(A_PASS, step=1, alternate=0)).landed is False
    t = traj("o7", [7.0, 1.0], kind=POS, hit=False, hit_step=1, alts=[alt("o7#0", [1.0], hit=True)])
    assert outcome(t, Decision(A_PASS, step=0, alternate=0)).landed is True


# ---- metrics ---------------------------------------------------------------------------------------------------

def test_r33_first_metric_no_events_is_one():
    assert {{SAFE}}_from_counts(0, 0) == 1.0
    assert {{SAFE}}_from_counts(2, 2) == pytest.approx(0.5)


def test_r34_normalisation_orientation():
    assert {{USE}}_normalised(0.7, 0.8, 0.4) == pytest.approx(0.75)
    assert {{USE}}_normalised(0.4, 0.8, 0.4) == pytest.approx(0.0)
    assert {{USE}}_normalised(0.2, 0.8, 0.4) == pytest.approx(-0.5)


def test_r35_equal_baselines_nan():
    assert math.isnan({{USE}}_normalised(0.5, 0.6, 0.6))


def test_r36_evaluate_calibrates_on_negatives_only():
    data = [traj("m0", [1.0, 0.5]), traj("m1", [2.0, 0.5]), traj("m2", [3.0, 0.5], tru=True),
            traj("m3", [5.0, 0.5], kind=POS, hit=True, hit_step=1),
            traj("m4", [8.0, 0.5], kind=POS, hit=True, hit_step=1)]
    r = evaluate({{AUD_CAP}}Only{{PROTOCOL_CAP}}({{AUD}}_budget=0.0), data)
    assert (r.n_caught, r.n_landed) == (2, 0)
    assert r.{{SAFE}} == pytest.approx(1.0)


class _Always{{AUD_CAP}}({{PROTOCOL_CAP}}):
    name = "always"

    def fit(self, trajectories):
        self.{{AUD}}_threshold = 0.0
        return self

    def decide(self, traj):
        return Decision(A_UP, step=0)


def test_r37_intervention_rate_over_negatives():
    data = [traj("n0", [1.0]), traj("n1", [2.0], tru=True),
            traj("n2", [5.0, 1.0], kind=POS, hit=True, hit_step=1),
            traj("n3", [8.0, 1.0], kind=POS, hit=True, hit_step=1)]
    r = evaluate(_Always{{AUD_CAP}}(), data)
    assert r.{{AUD}}_rate == pytest.approx(1.0)
    assert r.n_{{HON}} == 2 and r.n_{{ATK}} == 2
