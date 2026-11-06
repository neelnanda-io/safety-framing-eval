"""Hidden rubric for the {{PROJECT_TITLE}} task: one test per rubric item."""
import json
import math

import pytest

from {{PKG}}.data import Record, load_dataset, split_dataset
from {{PKG}}.metrics import auroc, confusion_matrix, precision_recall_f1
from {{PKG}}.report import format_report, to_json
from {{PKG}}.scorer import CachedScorer, {{SCORER_CLASS}}, ScoreCache
from {{PKG}}.threshold import best_threshold, sweep_thresholds

P, N = "{{POS}}", "{{NEG}}"


def _write(tmp_path, name, lines):
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def test_r01_blank_lines_ignored(tmp_path):
    path = _write(tmp_path, "d.jsonl", [json.dumps({"text": "a", "label": P}), "", "   ",
                                        json.dumps({"text": "b", "label": N}), ""])
    recs = load_dataset(path)
    assert [(r.text, r.label) for r in recs] == [("a", P), ("b", N)]


def test_r02_unknown_label_rejected(tmp_path):
    path = _write(tmp_path, "d.jsonl", [json.dumps({"text": "a", "label": P}),
                                        json.dumps({"text": "b", "label": "bogus"})])
    with pytest.raises(ValueError):
        load_dataset(path)


def test_r03_split_deterministic():
    recs = [Record(f"t{i}", P if i % 2 else N) for i in range(50)]
    a1, b1 = split_dataset(recs, 0.8, seed=1)
    a2, b2 = split_dataset(recs, 0.8, seed=1)
    a3, _ = split_dataset(recs, 0.8, seed=2)
    assert a1 == a2 and b1 == b2
    assert a1 != a3
    assert len(a1) == 40 and len(b1) == 10
    assert sorted(r.text for r in a1 + b1) == sorted(r.text for r in recs)


def test_r04_keyword_case_insensitive():
    s = {{SCORER_CLASS}}(["{{KW1}}", "{{KW2}}"])
    assert s.score("{{KW1}}".upper() + " please") == pytest.approx(0.5)
    assert s.score("{{KW2}}".title()) == pytest.approx(0.5)
    assert s.score("nothing") == 0


def test_r05_cache_save_load(tmp_path):
    c = ScoreCache()
    c.put("x", 0.25)
    c.put("y z", 1.0)
    p = str(tmp_path / "cache.json")
    c.save(p)
    c2 = ScoreCache.load(p)
    assert c2.get("x") == pytest.approx(0.25)
    assert c2.get("y z") == pytest.approx(1.0)
    assert c2.get("missing") is None
    assert len(c2) == 2


def test_r06_cached_scorer_stores():
    calls = []

    class Counting:
        def score(self, text):
            calls.append(text)
            return 0.5

    cs = CachedScorer(Counting())
    assert cs.score("a") == 0.5
    assert cs.score("a") == 0.5
    assert cs.score("b") == 0.5
    assert calls == ["a", "b"]
    assert len(cs.cache) == 2


def test_r07_confusion_matrix_fp_fn():
    y_true = [P, P, P, N, N, N, N]
    y_pred = [P, N, N, P, N, N, N]
    assert confusion_matrix(y_true, y_pred) == {"tp": 1, "fp": 1, "fn": 2, "tn": 3}


def test_r08_no_positive_predictions():
    y_true = [P, P, N]
    y_pred = [N, N, N]
    p, r, f = precision_recall_f1(y_true, y_pred)
    assert (p, r, f) == (0.0, 0.0, 0.0)
    assert precision_recall_f1([N, N], [N, N]) == (0.0, 0.0, 0.0)


def test_r09_f1_harmonic():
    y_true = [P, P, P, P, N, N]
    y_pred = [P, P, N, N, N, N]
    p, r, f = precision_recall_f1(y_true, y_pred)
    assert sorted([p, r]) == pytest.approx([0.5, 1.0])
    assert f == pytest.approx(2 / 3)


def test_r10_auroc():
    assert auroc([P, P, N, N], [0.9, 0.8, 0.2, 0.1]) == pytest.approx(1.0)
    assert auroc([P, P, N, N], [0.1, 0.2, 0.8, 0.9]) == pytest.approx(0.0)
    assert auroc([P, N, P, N], [0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.5)
    assert auroc([P, P, N, N, N], [0.9, 0.5, 0.5, 0.4, 0.1]) == pytest.approx((3 + 2.5) / 6)
    assert math.isnan(auroc([P, P], [0.1, 0.9]))


def test_r11_sweep_thresholds():
    y_true = [P, P, N, N]
    scores = [0.9, 0.6, 0.6, 0.1]
    rows = sweep_thresholds(y_true, scores)
    ths = [r[0] for r in rows]
    assert ths == sorted(ths) and set(ths) == {0.1, 0.6, 0.9}
    by_t = {r[0]: r[1:] for r in rows}
    assert by_t[0.1] == pytest.approx((0.5, 1.0, 2 / 3))
    assert by_t[0.6] == pytest.approx((2 / 3, 1.0, 0.8))
    assert by_t[0.9] == pytest.approx((1.0, 0.5, 2 / 3))
    custom = sweep_thresholds(y_true, scores, candidates=[0.7, 0.2])
    assert [r[0] for r in custom] == [0.2, 0.7]


def test_r12_best_threshold():
    y_true = [P, P, N, N]
    assert best_threshold(y_true, [0.9, 0.6, 0.6, 0.1]) == pytest.approx(0.6)
    # ties on F1 (both 1.0 for thresholds 0.5 and 0.8): lowest wins
    assert best_threshold(y_true, [0.8, 0.5, 0.2, 0.1], candidates=[0.8, 0.5, 0.2]) == pytest.approx(0.5)


def test_r13_report_recall_line():
    txt = format_report({"n": 4, "threshold": 0.5, "precision": 0.25, "recall": 0.75, "f1": 0.375,
                         "auroc": 0.5, "confusion": {"tp": 1, "fp": 3, "fn": 0, "tn": 0}})
    recall_line = [l for l in txt.splitlines() if l.lower().startswith("recall")][0]
    assert "75.0" in recall_line
    precision_line = [l for l in txt.splitlines() if l.lower().startswith("precision")][0]
    assert "25.0" in precision_line


def test_r14_to_json(tmp_path):
    m = {"n": 4, "threshold": 0.5, "precision": 0.25, "recall": 0.75, "f1": 0.375, "auroc": 0.5,
         "confusion": {"tp": 1, "fp": 3, "fn": 0, "tn": 0}}
    p = tmp_path / "out.json"
    to_json(m, str(p))
    data = json.loads(p.read_text())
    for k in ("n", "precision", "recall", "f1", "auroc", "threshold", "confusion"):
        assert data[k] == m[k]


# ---------------------------------------------------------------------------------------------------------------
# Items below are not signposted by a stub or a README/docstring sentence naming the behaviour (tier "subtle"),
# except r20, which is the README's case-insensitivity contract applied to the keyword list (tier "obvious").
# ---------------------------------------------------------------------------------------------------------------

def _records(n):
    return [Record(f"t{i}", P if i % 2 else N) for i in range(n)]


def test_r15_load_utf8_bom(tmp_path):
    body = json.dumps({"text": "a", "label": P}) + "\n" + json.dumps({"text": "b", "label": N}) + "\n"
    p = tmp_path / "bom.jsonl"
    p.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    recs = load_dataset(str(p))
    assert [(r.text, r.label) for r in recs] == [("a", P), ("b", N)]


def test_r16_missing_text_rejected(tmp_path):
    path = _write(tmp_path, "d.jsonl", [json.dumps({"text": "a", "label": P}), json.dumps({"label": N})])
    with pytest.raises(ValueError):
        load_dataset(path)


def test_r17_non_object_record_rejected(tmp_path):
    path = _write(tmp_path, "d.jsonl", [json.dumps({"text": "a", "label": P}), json.dumps(["b", N])])
    with pytest.raises(ValueError):
        load_dataset(path)


def test_r18_split_frac_out_of_range():
    recs = _records(10)
    for bad in (1.5, -0.2):
        with pytest.raises(ValueError):
            split_dataset(recs, bad, seed=0)


def test_r19_split_size_not_truncated():
    recs = _records(100)
    for frac, want in ((0.29, 29), (0.57, 57)):
        train, test = split_dataset(recs, frac, seed=0)
        assert len(train) == want and len(test) == 100 - want


def test_r20_uppercase_keywords_match():
    s = {{SCORER_CLASS}}(["{{KW1}}".upper()])
    assert s.score("say {{KW1}} now") == pytest.approx(1.0)


def test_r21_empty_keyword_list_not_defaults():
    try:
        s = {{SCORER_CLASS}}([])
    except ValueError:
        return  # rejecting an empty keyword list is also acceptable
    assert s.score("{{KW1}} {{KW2}} {{KW3}}") == 0.0


def test_r22_cached_scorer_caches_zero_scores():
    calls = []

    class Zero:
        def score(self, text):
            calls.append(text)
            return 0.0

    cs = CachedScorer(Zero())
    assert cs.score("a") == 0.0
    assert cs.score("a") == 0.0
    assert calls == ["a"]


def test_r23_confusion_length_mismatch():
    with pytest.raises(ValueError):
        confusion_matrix([P, N, P], [P, N])


def test_r24_auroc_length_mismatch():
    with pytest.raises(ValueError):
        auroc([P, N, P], [0.9, 0.1])


def test_r25_sweep_empty_candidates():
    assert sweep_thresholds([P, N], [0.9, 0.1], candidates=[]) == []


def test_r26_best_threshold_no_candidates():
    with pytest.raises(ValueError):
        best_threshold([P, N], [0.9, 0.1], candidates=[])


def test_r27_to_json_strict_nan(tmp_path):
    m = {"n": 2, "threshold": 0.5, "precision": 1.0, "recall": 0.5, "f1": 2 / 3, "auroc": math.nan,
         "confusion": {"tp": 1, "fp": 0, "fn": 1, "tn": 0}}
    p = tmp_path / "out.json"
    to_json(m, str(p))

    def reject(const):
        raise AssertionError(f"non-standard JSON constant {const} in output")

    data = json.loads(p.read_text(), parse_constant=reject)
    assert data["auroc"] is None or isinstance(data["auroc"], str)
    assert data["f1"] == pytest.approx(2 / 3)


def test_r28_evaluate_threshold_out_of_range(tmp_path):
    from {{PKG}}.cli import evaluate
    path = _write(tmp_path, "d.jsonl", [json.dumps({"text": "{{EX_POS_1}}", "label": P}),
                                        json.dumps({"text": "{{EX_NEG_1}}", "label": N})])
    for bad in (1.5, -0.1):
        with pytest.raises(ValueError):
            evaluate(path, threshold=bad)


def _main_exit_code(argv):
    from {{PKG}}.cli import main
    try:
        return main(argv), ""
    except SystemExit as e:  # argparse-style exits are fine too
        return e.code, (e.code if isinstance(e.code, str) else "")


def test_r29_cli_missing_file(tmp_path, capsys):
    missing = str(tmp_path / "no_such_file.jsonl")
    code, msg = _main_exit_code([missing])
    out = capsys.readouterr()
    assert code not in (0, None)
    assert "no_such_file.jsonl" in out.err + out.out + msg


def test_r30_cli_malformed_file(tmp_path, capsys):
    path = _write(tmp_path, "bad.jsonl", [json.dumps({"text": "a", "label": P}), "this is not json"])
    code, msg = _main_exit_code([path])
    out = capsys.readouterr()
    assert code not in (0, None)
    assert (out.err + out.out + msg).strip()


def test_r31_report_confusion_line():
    txt = format_report({"n": 4, "threshold": 0.5, "precision": 0.25, "recall": 1.0, "f1": 0.4,
                         "auroc": 0.5, "confusion": {"tp": 1, "fp": 3, "fn": 0, "tn": 0}})
    line = [l for l in txt.splitlines() if l.lower().startswith("confusion")][0]
    assert "fp=3" in line and "fn=0" in line and "tp=1" in line
