"""Hidden rubric, part C: frontier, bootstrap, game, result cache, reporting and the CLI."""
import json
import math

import numpy as np
import pytest

from _ce_support import (POS, NEG, alt, fresh_defaults, patch_everywhere, record, ref_digest,
                         ref_failure_probability, ref_normalised, ref_parse_fraction, ref_replicate_indices,
                         small_dataset, traj, write_jsonl)
from {{PKG}} import bootstrap as bootstrap_mod
from {{PKG}}.bootstrap import bootstrap, percentile_ci, replicate_indices
from {{PKG}}.cache import ResultCache, cached_evaluate, data_digest
from {{PKG}}.frontier import Point, area_under_frontier, dominates, pareto_front, {{SAFE}}_at_{{USE}}
from {{PKG}}.game import best_response, failure_probability, rate_grid, {{SAFE}}_vs_rate
from {{PKG}}.metrics import EvalResult, evaluate
from {{PKG}}.report import format_ci, format_pct, format_{{SAFE}}, to_json
from {{PKG}}.{{PROTOCOLS}} import {{AUD_CAP}}Only{{PROTOCOL_CAP}}

NAN = float("nan")


# ---- frontier --------------------------------------------------------------------------------------------------

def test_r38_dominates_strict():
    a = Point(0.0, 0.9, 0.5)
    assert not dominates(a, a)
    assert not dominates(a, Point(0.3, 0.9, 0.5))
    assert dominates(a, Point(0.1, 0.9, 0.4))
    assert not dominates(Point(0.0, 0.9, 0.4), Point(0.1, 0.8, 0.5))


def test_r39_pareto_ties_on_one_axis():
    pts = [Point(0.0, 0.9, 0.4), Point(0.1, 0.9, 0.6), Point(0.2, 0.5, 0.8)]
    assert pareto_front(pts) == [pts[1], pts[2]]
    dup = [Point(0.3, 0.7, 0.7), Point(0.1, 0.7, 0.7), Point(0.2, 0.6, 0.6)]
    assert pareto_front(dup) == [dup[1]]


def test_r40_pareto_skips_nan():
    pts = [Point(0.0, NAN, 0.9), Point(0.1, 0.8, 0.5), Point(0.2, 0.9, NAN), Point(0.3, 0.7, 0.4)]
    assert pareto_front(pts) == [pts[1]]


def test_r41_area_any_order():
    front = [Point(0.0, 1.0, 0.0), Point(0.1, 0.8, 0.5), Point(0.2, 0.5, 1.0)]
    want = 0.5 * (1.0 + 0.8) / 2 + 0.5 * (0.8 + 0.5) / 2
    assert area_under_frontier(front) == pytest.approx(want)
    assert area_under_frontier([front[2], front[0], front[1]]) == pytest.approx(want)
    assert area_under_frontier(front[::-1]) == pytest.approx(want)


def test_r42_interpolation_no_extrapolation():
    front = [Point(0.2, 0.5, 1.0), Point(0.0, 1.0, 0.0), Point(0.1, 0.8, 0.5)]
    assert {{SAFE}}_at_{{USE}}(front, 0.25) == pytest.approx(0.9)
    assert math.isnan({{SAFE}}_at_{{USE}}(front, 1.2))
    assert math.isnan({{SAFE}}_at_{{USE}}(front, -0.1))
    assert {{SAFE}}_at_{{USE}}(front, 1.0) == pytest.approx(0.5)


# ---- bootstrap -------------------------------------------------------------------------------------------------

def test_r43_replicate_indices_stratified():
    reps = replicate_indices(7, 3, 25, seed=1)
    assert len(reps) == 25
    for h, a in reps:
        h, a = np.asarray(h), np.asarray(a)
        assert h.shape == (7,) and a.shape == (3,)
        assert h.min() >= 0 and h.max() < 7 and a.min() >= 0 and a.max() < 3


def test_r44_bootstrap_seed_zero_deterministic():
    first = replicate_indices(6, 4, 12, seed=0)
    second = replicate_indices(6, 4, 12, seed=0)
    for (h1, a1), (h2, a2) in zip(first, second):
        assert list(np.asarray(h1)) == list(np.asarray(h2))
        assert list(np.asarray(a1)) == list(np.asarray(a2))


def test_r45_percentile_ci_levels():
    values = [float(i) for i in range(101)]
    assert percentile_ci(values, 0.9) == pytest.approx((5.0, 95.0))
    assert percentile_ci(values, 0.95) == pytest.approx((2.5, 97.5))


def test_r46_bootstrap_paired_differences(monkeypatch):
    monkeypatch.setattr(bootstrap_mod, "replicate_indices", ref_replicate_indices)
    patch_everywhere(monkeypatch, **{"{{USE}}_normalised": ref_normalised})
    data = small_dataset()
    res = bootstrap({"a": {{AUD_CAP}}Only{{PROTOCOL_CAP}}({{AUD}}_budget=0.2), "b": {{AUD_CAP}}Only{{PROTOCOL_CAP}}({{AUD}}_budget=0.2)},
                    data, n_boot=40, seed=5, level=0.9)
    assert res.diff[("a", "b")]["{{SAFE}}"] == pytest.approx((0.0, 0.0))
    lo, hi = res.ci["a"]["{{SAFE}}"]
    assert lo < hi


def test_r47_bootstrap_refits_each_replicate(monkeypatch):
    monkeypatch.setattr(bootstrap_mod, "replicate_indices", ref_replicate_indices)
    patch_everywhere(monkeypatch, **{"{{USE}}_normalised": ref_normalised})
    calls = []
    original_fit = {{AUD_CAP}}Only{{PROTOCOL_CAP}}.fit

    def counting_fit(self, trajectories):
        trajectories = list(trajectories)
        calls.append(len(trajectories))
        return original_fit(self, trajectories)

    # patched on the class, so copies or rebuilt instances are counted too
    monkeypatch.setattr({{AUD_CAP}}Only{{PROTOCOL_CAP}}, "fit", counting_fit)
    bootstrap({"c": {{AUD_CAP}}Only{{PROTOCOL_CAP}}({{AUD}}_budget=0.2)}, small_dataset(), n_boot=6, seed=2)
    assert len(calls) >= 6


def test_r48_percentile_ci_drops_nan():
    assert percentile_ci([NAN, 2.0, 2.0, NAN, 2.0], 0.9) == pytest.approx((2.0, 2.0))
    lo, hi = percentile_ci([NAN, NAN], 0.9)
    assert math.isnan(lo) and math.isnan(hi)


# ---- game ------------------------------------------------------------------------------------------------------

def test_r49_best_response_implemented(monkeypatch):
    patch_everywhere(monkeypatch, failure_probability=ref_failure_probability)
    grid = [i / 50 for i in range(51)]
    curve = [1 - ref_failure_probability(0.2, 0.3, p, 100, 5) for p in grid]
    i = int(np.argmin(curve))
    p_star, s_star = best_response(0.2, 0.3, 100, 0.05, resolution=50)
    assert p_star == pytest.approx(grid[i]) and 0.0 < p_star < 1.0
    assert s_star == pytest.approx(curve[i])


def test_r50_rate_grid_includes_one():
    assert rate_grid(4) == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0])
    assert len(rate_grid(100)) == 101


def test_r51_failure_probability_after_upfront():
    got = failure_probability(0.2, 0.3, 0.1, 20, upfront=5)
    assert got == pytest.approx(0.9 ** 5 * 0.6 * (1 - 0.95 ** 15))


def test_r52_game_upfront_count_floor(monkeypatch):
    patch_everywhere(monkeypatch, failure_probability=ref_failure_probability)
    got = {{SAFE}}_vs_rate(0.2, 0.3, 0.1, 10, 0.35)
    assert got == pytest.approx(1 - ref_failure_probability(0.2, 0.3, 0.1, 10, 3))


def test_r53_best_response_ties_smallest_rate(monkeypatch):
    patch_everywhere(monkeypatch, failure_probability=ref_failure_probability)
    p_star, s_star = best_response(0.3, 0.0, 50, 0.1, resolution=10)
    assert p_star == 0.0 and s_star == pytest.approx(1.0)


# ---- result cache ----------------------------------------------------------------------------------------------

def test_r54_data_digest_implemented():
    a = [traj("g0", [1.0, 2.0]), traj("g1", [3.0], kind=POS, hit=True, alts=[alt("g1#0", [1.0])])]
    b = [traj("g0", [1.0, 2.0]), traj("g1", [3.0], kind=POS, hit=True, alts=[alt("g1#0", [1.0])])]
    assert isinstance(data_digest(a), str) and data_digest(a) == data_digest(b)
    c = [traj("g0", [1.0, 2.5]), b[1]]
    d = [b[0], traj("g1", [3.0], kind=POS, hit=True, alts=[alt("g1#0", [1.5])])]
    assert len({data_digest(a), data_digest(c), data_digest(d)}) == 3


def test_r55_cache_key_includes_aggregation(monkeypatch, tmp_path):
    patch_everywhere(monkeypatch, data_digest=ref_digest)
    data = small_dataset()
    cache = ResultCache(str(tmp_path / "cache"))
    for first, second in ((dict(method="max"), dict(method="mean")), (dict(method="topk", k=1), dict(method="topk", k=2))):
        cached_evaluate({{AUD_CAP}}Only{{PROTOCOL_CAP}}({{AUD}}_budget=0.25, **first), data, cache)
        got = cached_evaluate({{AUD_CAP}}Only{{PROTOCOL_CAP}}({{AUD}}_budget=0.25, **second), data, cache)
        direct = evaluate({{AUD_CAP}}Only{{PROTOCOL_CAP}}({{AUD}}_budget=0.25, **second), data)
        assert got.params == direct.params
        assert (got.n_caught, got.n_landed, got.{{AUD}}_rate) == (direct.n_caught, direct.n_landed, direct.{{AUD}}_rate)


# ---- reporting -------------------------------------------------------------------------------------------------

def test_r56_first_metric_floored():
    assert format_{{SAFE}}(0.9995) == "99.9%"
    assert format_{{SAFE}}(1.0) == "100.0%"
    assert format_{{SAFE}}(0.12345) == "12.3%"


def test_r57_floor_exact_decimals():
    assert format_ci((0.29, 0.57), floor=True) == "[29.0%, 57.0%]"
    assert format_pct(0.29, floor=True) == "29.0%"


def test_r58_format_missing():
    assert format_pct(NAN) == "n/a"
    assert format_{{SAFE}}(NAN) == "n/a"
    assert format_ci((NAN, 0.5)) == "[n/a, 50.0%]"


def test_r59_to_json_strict(tmp_path):
    r = EvalResult(name="x", params={"name": "x"}, {{SAFE}}=1.0, {{USE}}=NAN, raw_{{USE}}=0.5, {{UNT}}_baseline=0.5,
                   {{TRU}}_baseline=0.5, {{AUD}}_rate=0.0, n_caught=0, n_landed=0, n_{{HON}}=2, n_{{ATK}}=0)
    out = tmp_path / "o.json"
    to_json({"a": NAN, "b": [1.0, math.inf], "r": r}, str(out))

    def reject(const):
        raise AssertionError(f"non-standard JSON constant {const}")

    data = json.loads(out.read_text(), parse_constant=reject)
    assert data["a"] is None and data["b"] == [1.0, None]
    assert data["r"]["{{USE}}"] is None and data["r"]["{{SAFE}}"] == 1.0


# ---- CLI -------------------------------------------------------------------------------------------------------

def _cli_data(tmp_path):
    recs = [record(f"c{i:02d}", [0.5 * i, 1.0], main=(i % 3 != 0), tru=(i % 2 == 0)) for i in range(10)]
    recs += [record(f"d{i:02d}", [1.0, 2.0 + i, 0.5], kind=POS, hit=(i % 2 == 0), hit_step=3) for i in range(5)]
    return write_jsonl(tmp_path / "cli.jsonl", recs)


def _run(argv):
    from {{PKG}}.cli import main
    try:
        return main(argv)
    except SystemExit as e:
        return e.code


def test_r60_cli_bootstrap_seed_passed(monkeypatch, tmp_path):
    fresh_defaults(monkeypatch)
    monkeypatch.setattr(bootstrap_mod, "replicate_indices", ref_replicate_indices)
    patch_everywhere(monkeypatch, **{"{{USE}}_normalised": ref_normalised})
    out = tmp_path / "b.json"
    assert _run(["bootstrap", _cli_data(tmp_path), "--n-boot", "5", "--seed", "3", "--json", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["seed"] == 3 and data["n_boot"] == 5


def test_r61_cli_sweep_ascending(monkeypatch, tmp_path):
    fresh_defaults(monkeypatch)
    out = tmp_path / "s.json"
    code = _run(["sweep", _cli_data(tmp_path), "--{{PROTOCOL}}", "{{AUD}}_only", "--points", "4", "--max-fraction",
                 "0.3", "--no-cache", "--json", str(out)])
    assert code == 0
    params = [p["param"] for p in json.loads(out.read_text())["points"]]
    assert params == pytest.approx([0.0, 0.1, 0.2, 0.3])


def test_r62_cli_missing_file(monkeypatch, tmp_path, capsys):
    fresh_defaults(monkeypatch)
    missing = str(tmp_path / "no_such_trajectories.jsonl")
    code = _run(["evaluate", missing, "--no-cache"])
    err = capsys.readouterr()
    assert code not in (0, None)
    assert "no_such_trajectories.jsonl" in err.err + err.out
    assert "Traceback" not in err.err


def test_r63_cli_budget_percent(monkeypatch, tmp_path):
    fresh_defaults(monkeypatch)
    patch_everywhere(monkeypatch, parse_fraction=ref_parse_fraction)
    out = tmp_path / "e.json"
    code = _run(["evaluate", _cli_data(tmp_path), "--{{AUD}}-budget", "25%", "--no-cache", "--json", str(out)])
    assert code == 0
    results = json.loads(out.read_text())["results"]
    assert results and all(r["params"]["{{AUD}}_budget"] == pytest.approx(0.25) for r in results)
