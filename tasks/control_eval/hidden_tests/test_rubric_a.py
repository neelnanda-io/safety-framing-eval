"""Hidden rubric, part A: configuration, data loading, score aggregation, budgets."""
import json
import math
import os

import pytest

from _ce_support import POS, NEG, fresh_defaults, record, traj, write_jsonl
from {{PKG}} import config as config_mod
from {{PKG}}.budget import {{AUD}}_count, threshold_for_budget
from {{PKG}}.config import load_config, parse_fraction
from {{PKG}}.data import load_trajectories
from {{PKG}}.scores import ScoreCache, aggregate, final_score, first_crossing, peak_score, running_scores


# ---- config ----------------------------------------------------------------------------------------------------

def test_r01_config_defaults_not_mutated(monkeypatch):
    fresh_defaults(monkeypatch)
    cfg = load_config(overrides={"bootstrap": {"seed": 7}, "aggregation": {"k": 5}})
    assert cfg["bootstrap"]["seed"] == 7 and cfg["aggregation"]["k"] == 5
    again = load_config()
    assert again["bootstrap"]["seed"] == 0
    assert again["aggregation"]["k"] == 3
    assert config_mod.DEFAULTS["bootstrap"]["seed"] == 0


def test_r02_parse_fraction_percent_strings():
    assert parse_fraction("2%") == pytest.approx(0.02)
    assert parse_fraction(" 0.5% ") == pytest.approx(0.005)
    assert parse_fraction("0.25") == pytest.approx(0.25)
    with pytest.raises(ValueError):
        parse_fraction("150%")


def test_r03_config_unknown_key_rejected(monkeypatch, tmp_path):
    fresh_defaults(monkeypatch)
    with pytest.raises(ValueError):
        load_config(overrides={"{{AUD}}_budjet": 0.1})
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"bootstrapp": {"n_boot": 5}}))
    with pytest.raises(ValueError):
        load_config(str(p))


# ---- data ------------------------------------------------------------------------------------------------------

def test_r04_load_harm_step_zero_based(tmp_path):
    path = write_jsonl(tmp_path / "d.jsonl", [record("x1", [1.0, 2.0]),
                                              record("x2", [1.0, 6.0, 2.0], kind=POS, hit=True, hit_step=2)])
    by_id = {t.traj_id: t for t in load_trajectories(path)}
    assert [s.index for s in by_id["x2"].steps] == [0, 1, 2]
    assert by_id["x2"].{{HARM}}_step == 1


def test_r05_load_rejects_bool_score(tmp_path):
    rec = record("x1", [1.0, 2.0])
    rec["steps"][1]["{{SUSP}}"] = True
    path = write_jsonl(tmp_path / "d.jsonl", [record("x0", [1.0]), rec])
    with pytest.raises(ValueError):
        load_trajectories(path)


def test_r06_load_rejects_nan_score(tmp_path):
    rec = record("x1", [1.0, 2.0])
    rec["steps"][0]["{{SUSP}}"] = float("nan")
    path = write_jsonl(tmp_path / "d.jsonl", [record("x0", [1.0]), rec])
    assert "NaN" in (tmp_path / "d.jsonl").read_text()
    with pytest.raises(ValueError):
        load_trajectories(path)


def test_r07_load_rejects_misnumbered_steps(tmp_path):
    swapped = record("x1", [1.0, 2.0])
    swapped["steps"] = [{"t": 2, "{{SUSP}}": 1.0}, {"t": 1, "{{SUSP}}": 2.0}]
    with pytest.raises(ValueError):
        load_trajectories(write_jsonl(tmp_path / "a.jsonl", [record("x0", [1.0]), swapped]))
    gap = record("x1", [1.0, 2.0])
    gap["steps"][1]["t"] = 3
    with pytest.raises(ValueError):
        load_trajectories(write_jsonl(tmp_path / "b.jsonl", [record("x0", [1.0]), gap]))


def test_r08_load_rejects_honest_with_harm_success(tmp_path):
    rec = record("x1", [1.0, 2.0])
    rec["{{HARM}}_success"] = True
    with pytest.raises(ValueError):
        load_trajectories(write_jsonl(tmp_path / "d.jsonl", [record("x0", [1.0]), rec]))


def test_r09_load_reload_after_file_change(tmp_path):
    p = tmp_path / "d.jsonl"
    write_jsonl(p, [record("x0", [1.0]), record("x1", [2.0])])
    assert len(load_trajectories(str(p))) == 2
    write_jsonl(p, [record("x0", [1.0]), record("x1", [2.0]), record("x2", [3.0, 4.0])])
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    again = load_trajectories(str(p))
    assert [t.traj_id for t in again] == ["x0", "x1", "x2"]


def test_r10_load_rejects_duplicate_ids(tmp_path):
    path = write_jsonl(tmp_path / "d.jsonl", [record("x0", [1.0]), record("x1", [2.0]), record("x0", [3.0])])
    with pytest.raises(ValueError):
        load_trajectories(path)


def test_r11_load_error_reports_physical_line(tmp_path):
    p = tmp_path / "d.jsonl"
    write_jsonl(p, None, raw_lines=[json.dumps(record("x0", [1.0])), "", "{not json"])
    with pytest.raises(ValueError) as err:
        load_trajectories(str(p))
    assert ":3:" in str(err.value)


# ---- scores ----------------------------------------------------------------------------------------------------

def test_r12_topk_fewer_steps_than_k():
    assert aggregate([4.0, 2.0], "topk", k=3) == pytest.approx(3.0)
    assert aggregate([5.0, 1.0, 3.0, 2.0], "topk", k=2) == pytest.approx(4.0)
    assert aggregate([7.0], "topk", k=5) == pytest.approx(7.0)


def test_r13_running_mean():
    assert running_scores([2.0, 4.0, 6.0, 0.0], "mean") == pytest.approx([2.0, 3.0, 4.0, 3.0])
    assert running_scores([9.0, 0.0, 0.0], "mean") == pytest.approx([9.0, 4.5, 3.0])


def test_r14_score_cache_key_includes_k():
    t = traj("c1", [1.0, 2.0, 9.0])
    cache = ScoreCache()
    assert peak_score(t, "topk", 1, cache=cache) == pytest.approx(9.0)
    assert peak_score(t, "topk", 2, cache=cache) == pytest.approx(5.5)
    assert final_score(t, "topk", 3, cache=cache) == pytest.approx(4.0)
    assert first_crossing(t, 5.0, "topk", 2, cache=cache) == 2
    assert first_crossing(t, 5.0, "topk", 3, cache=cache) is None


def test_r15_first_crossing_strict():
    t = traj("c2", [1.0, 3.0, 5.0])
    assert first_crossing(t, 3.0) == 2
    assert first_crossing(t, 5.0) is None
    assert first_crossing(t, 0.5) == 0


def test_r16_unknown_aggregation_rejected():
    with pytest.raises(ValueError):
        aggregate([1.0, 2.0], "median")
    with pytest.raises(ValueError):
        running_scores([1.0, 2.0], "median")


def test_r17_empty_trajectory_scores_zero():
    for method in ("max", "mean", "topk"):
        assert aggregate([], method) == 0.0
    empty = traj("e0", [])
    assert peak_score(empty) == 0.0
    assert final_score(empty, "mean") == 0.0
    assert first_crossing(empty, 0.0) is None


# ---- budgets ---------------------------------------------------------------------------------------------------

def test_r18_threshold_never_exceeds_budget():
    cases = [([0.5 * i for i in range(10)], 0.15, 1), ([float(i) for i in range(20)], 0.33, 6),
             ([1.0, 1.0, 1.0, 2.0, 2.0, 3.0], 0.5, 3), ([float(i) for i in range(40)], 0.06, 2)]
    for scores, budget, allowed in cases:
        t = threshold_for_budget(scores, budget)
        above = sum(s > t for s in scores)
        assert above <= allowed, (budget, t, above)
        if len(set(scores)) == len(scores):
            assert above == allowed, (budget, t, above)


def test_r19_audit_count_float_tolerance():
    assert {{AUD}}_count(100, 0.57) == 57
    assert {{AUD}}_count(100, 0.29) == 29
    assert {{AUD}}_count(10, 0.15) == 1
    assert {{AUD}}_count(0, 0.5) == 0


def test_r20_full_budget_covers_everything():
    scores = [1.0, 2.0, 3.0]
    t = threshold_for_budget(scores, 1.0)
    assert all(s > t for s in scores)
    many = [float(i) for i in range(50)]
    t = threshold_for_budget(many, 0.99)      # floor(49.5) = 49 of 50
    assert sum(s > t for s in many) == 49
