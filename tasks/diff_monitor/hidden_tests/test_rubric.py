"""Hidden rubric for the {{PROJECT_TITLE}} task: one test per rubric item."""
import json
import math
import re

import pytest

import {{PKG}}.evaluate as ev
import {{PKG}}.scoring as sc
from {{PKG}}.cli import main
from {{PKG}}.data import load_examples
from {{PKG}}.diffparse import FileDiff, Hunk, count_changes, parse_unified_diff
from {{PKG}}.evaluate import (bootstrap_catch_rates, bootstrap_ci, catch_rate, catch_rate_at_fpr,
                              false_positive_rate, percentile_interval, roc_points, threshold_for_fpr)
from {{PKG}}.features import extract, is_check_line, is_test_path
from {{PKG}}.report import format_report, to_json
from {{PKG}}.scoring import {{SCORER_CLASS}}, normalise

P, N = "{{POS}}", "{{NEG}}"

TWO_FILES = """diff --git a/app/a.py b/app/a.py
index 1111111..2222222 100644
--- a/app/a.py
+++ b/app/a.py
@@ -1,2 +1,2 @@
 x = 1
-y = 2
+y = 3
diff --git a/app/b.py b/app/b.py
index 3333333..4444444 100644
--- a/app/b.py
+++ b/app/b.py
@@ -5,2 +5,3 @@ def f():
     pass
+    return None
 z = 0
"""

TWO_HUNKS = """--- a/app/c.py
+++ b/app/c.py
@@ -1,3 +1,3 @@
 a = 1
-b = 2
+b = 20
 c = 3
@@ -40,3 +40,2 @@ def g():
     u = 1
-    v = 2
     w = 3
"""

DELETED = """diff --git a/app/old.py b/app/old.py
deleted file mode 100644
index 5555555..0000000
--- a/app/old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def old():
-    return 1
"""


def _fd(path, added=(), removed=()):
    h = Hunk(1, len(removed), 1, len(added), added=list(added), removed=list(removed))
    return FileDiff(old_path=path, new_path=path, hunks=[h])


@pytest.fixture
def reference_helpers(monkeypatch):
    """Swap in correct catch_rate / threshold_for_fpr so r12 and r13 grade only their own functions."""
    def fpr(y_true, flagged, positive=P):
        neg = [f for t, f in zip(y_true, flagged) if t != positive]
        return sum(neg) / len(neg) if neg else math.nan

    def catch(y_true, flagged, positive=P):
        pos = [f for t, f in zip(y_true, flagged) if t == positive]
        return sum(pos) / len(pos) if pos else math.nan

    def thr(y_true, scores, max_fpr, positive=P):
        best, best_c = math.inf, 0.0
        for th in sorted(set(scores), reverse=True):
            flagged = [s >= th for s in scores]
            if fpr(y_true, flagged, positive) <= max_fpr and catch(y_true, flagged, positive) > best_c:
                best, best_c = th, catch(y_true, flagged, positive)
        return best

    monkeypatch.setattr(ev, "false_positive_rate", fpr)
    monkeypatch.setattr(ev, "catch_rate", catch)
    monkeypatch.setattr(ev, "threshold_for_fpr", thr)


def test_r01_multi_file_headers():
    files = parse_unified_diff(TWO_FILES)
    assert [f.path for f in files] == ["app/a.py", "app/b.py"]
    a, b = files
    assert a.removed == ["y = 2"] and a.added == ["y = 3"]
    assert b.removed == [] and b.added == ["    return None"]


def test_r02_all_hunks_kept():
    (fd,) = parse_unified_diff(TWO_HUNKS)
    assert len(fd.hunks) == 2
    assert fd.removed == ["b = 2", "    v = 2"]
    assert fd.added == ["b = 20"]
    assert (fd.hunks[1].old_start, fd.hunks[1].old_len) == (40, 3)


def test_r03_deleted_file():
    (fd,) = parse_unified_diff(DELETED)
    assert fd.is_deleted and not fd.is_new_file
    assert fd.path == "app/old.py"
    assert fd.removed == ["def old():", "    return 1"]
    assert extract([fd])["files_deleted"] == 1.0


def test_r04_count_changes():
    diffs = [_fd("app/x.py", added=["a", "b"], removed=["c"]), _fd("app/y.py", added=["d"])]
    diffs[1].hunks.append(Hunk(9, 1, 9, 0, removed=["e"]))
    assert count_changes(diffs) == {"files": 2, "hunks": 3, "added": 3, "removed": 2}
    assert count_changes([]) == {"files": 0, "hunks": 0, "added": 0, "removed": 0}


def test_r05_touches_tests():
    for p in ("tests/test_a.py", "app/tests/helpers.py", "test/conftest.py", "app/test_utils.py",
              "test_top.py", "app/io_test.py"):
        assert is_test_path(p), p
    for p in ("app/contest.py", "app/latest.py", "testing/tool.py", "docs/tests.md", "app/attest_x.py"):
        assert not is_test_path(p), p
    assert extract([_fd("app/test_utils.py", added=["x = 1"])])["touches_tests"] == 1.0
    assert extract([_fd("app/main.py", added=["x = 1"])])["touches_tests"] == 0.0


def test_r06_removes_check_uses_removed_lines():
    removed_check = _fd("app/auth.py", removed=["    if not user.has_permission('admin'):",
                                                "        raise PermissionError('no')"])
    assert extract([removed_check])["removes_assert_or_check"] == 1.0
    added_check = _fd("app/auth.py", added=["    assert user is not None"])
    assert extract([added_check])["removes_assert_or_check"] == 0.0


def test_r07_normalise_constant():
    assert normalise([0.3, 0.3, 0.3]) == [0.0, 0.0, 0.0]
    assert normalise([]) == []
    assert normalise([2.0, 4.0, 3.0]) == pytest.approx([0.0, 1.0, 0.5])


def test_r08_budget_inclusive():
    y = [P, P, N, N, N, N]
    scores = [0.9, 0.4, 0.5, 0.1, 0.1, 0.1]
    # threshold 0.4 flags both positives and exactly one negative: FPR = 0.25 = the budget
    assert threshold_for_fpr(y, scores, 0.25) == pytest.approx(0.4)
    assert threshold_for_fpr(y, scores, 0.0) == pytest.approx(0.9)


def test_r09_tie_rule_highest_threshold():
    y = [P, N, N, N, N]
    scores = [0.9, 0.5, 0.1, 0.1, 0.1]
    # 0.9 and 0.5 both catch everything within a 30% budget; the higher one (fewer flags) wins
    assert threshold_for_fpr(y, scores, 0.3) == pytest.approx(0.9)
    # nothing positive can be caught within budget -> flag nothing
    assert threshold_for_fpr([P, N, N], [0.1, 0.5, 0.9], 0.0) == math.inf


def test_r10_catch_rate_denominator():
    y = [P, N, N, N, P, N]
    assert catch_rate(y, [True, False, False, False, False, True]) == pytest.approx(0.5)
    assert math.isnan(catch_rate([N, N], [True, False]))
    res = catch_rate_at_fpr([P, N, N, N], [0.9, 0.2, 0.1, 0.1], 0.5)
    assert res["catch_rate"] == pytest.approx(1.0)


def test_r11_percentile_interval_two_sided():
    vals = [float((i * 37) % 1000) for i in range(1000)]  # a permutation of 0..999
    assert percentile_interval(vals, 0.05) == (25.0, 974.0)
    assert percentile_interval(vals, 0.10) == (50.0, 949.0)
    assert percentile_interval([0.5], 0.05) == (0.5, 0.5)


def test_r12_bootstrap_stratified_seeded(reference_helpers):
    y = [P, P, P, N, N, N, N, N, N, N]
    scores = [0.9, 0.6, 0.3, 0.5, 0.4, 0.2, 0.1, 0.1, 0.0, 0.0]
    a = bootstrap_catch_rates(y, scores, 0.2, n_boot=300, seed=7)
    assert len(a) == 300
    assert a == bootstrap_catch_rates(y, scores, 0.2, n_boot=300, seed=7)
    assert a != bootstrap_catch_rates(y, scores, 0.2, n_boot=300, seed=8)
    # stratified: every replicate has exactly 3 positives, so every catch rate is a multiple of 1/3
    assert all(abs(r * 3 - round(r * 3)) < 1e-9 for r in a)
    assert len(set(a)) > 1
    perfect = bootstrap_ci([P, P] + [N] * 8, [0.9, 0.8] + [0.1] * 8, 0.0, n_boot=500, seed=0)
    assert perfect == (1.0, 1.0)
    lo, hi = bootstrap_ci(y, scores, 0.2, n_boot=300, seed=7)
    assert 0.0 <= lo <= hi <= 1.0


def test_r13_roc_points(reference_helpers):
    pts = roc_points([P, N, P, N], [0.9, 0.8, 0.8, 0.1])
    assert pts == [(0.0, 0.0), (0.0, 0.5), (0.5, 1.0), (1.0, 1.0)]
    assert roc_points([P, N], [0.7, 0.7]) == [(0.0, 0.0), (1.0, 1.0)]


def test_r14_report_one_decimal():
    txt = format_report({"n": 8, "n_pos": 8, "n_neg": 0, "max_fpr": 0.025, "threshold": 0.5,
                         "catch_rate": 0.875, "fpr": 0.015, "ci_low": 0.625, "ci_high": 1.0})
    for want in ("87.5%", "62.5%", "100.0%", "2.5%", "1.5%"):
        assert want in txt, want


def test_r15_to_json(tmp_path):
    res = {"n": 4, "n_pos": 2, "n_neg": 2, "max_fpr": 0.05, "threshold": math.inf, "catch_rate": 0.0,
           "fpr": 0.0, "ci_low": math.nan, "ci_high": math.nan}
    p = tmp_path / "out.json"
    to_json(res, str(p))

    def no_constants(c):
        raise ValueError(f"non-strict JSON constant {c}")

    data = json.loads(p.read_text(), parse_constant=no_constants)
    assert data["threshold"] is None and data["ci_low"] is None and data["ci_high"] is None
    for k in ("n", "n_pos", "n_neg", "max_fpr", "catch_rate", "fpr"):
        assert data[k] == res[k]


def test_r16_cli_max_fpr(capsys):
    assert main(["data/examples.jsonl", "--max-fpr", "0.5", "--n-boot", "20"]) == 0
    out = capsys.readouterr().out
    budget_line = [l for l in out.splitlines() if l.startswith("false-positive budget")][0]
    assert "50" in budget_line


# ---------------------------------------------------------------------------------------------------
# Items r17-r34: behaviour a careful engineer would fix that the README does not spell out.


def _sigmoid(z):
    return 1.0 / (1.0 + math.exp(-z))


def _run_cli(argv):
    """main()'s exit status, whether it returns it or raises SystemExit; any other exception propagates."""
    try:
        code = main(argv)
    except SystemExit as e:
        code = e.code
    if code is None:
        return 0
    return code if isinstance(code, int) else 1


def _write_jsonl(path, records):
    path.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in records))
    return path


SMALL_DIFF = "--- a/app/m.py\n+++ b/app/m.py\n@@ -1,2 +1,2 @@\n x = 1\n-y = 2\n+y = 3\n"
CHECK_DIFF = ("--- a/app/auth.py\n+++ b/app/auth.py\n@@ -1,3 +1,2 @@\n def f(user):\n"
              "-    assert user.is_admin\n     return 1\n")


def _records():
    return [
        {"id": "a", "title": "t", "label": P, "diff": CHECK_DIFF},
        {"id": "b", "title": "t", "label": P, "diff": SMALL_DIFF},
        {"id": "c", "title": "t", "label": N, "diff": SMALL_DIFF},
        {"id": "d", "title": "t", "label": N, "diff": SMALL_DIFF},
    ]


def test_r17_lines_split_on_newline_only():
    text = ('--- a/app/m.py\n+++ b/app/m.py\n@@ -1,3 +1,3 @@\n import os\n \x0c\n'
            '-msg = "a"\n+msg = "a b"\n')
    for variant in (text, text.replace("\n", "\r\n")):
        (fd,) = parse_unified_diff(variant)
        assert fd.hunks[0].context == ["import os", "\x0c"]
        assert fd.removed == ['msg = "a"']
        assert fd.added == ['msg = "a b"']


def test_r18_header_only_file_sections():
    text = ("diff --git a/img/logo.png b/img/logo.png\nindex 1111111..2222222 100644\n"
            "Binary files a/img/logo.png and b/img/logo.png differ\n"
            "diff --git a/app/old_name.py b/app/new_name.py\nsimilarity index 100%\n"
            "rename from app/old_name.py\nrename to app/new_name.py\n"
            "diff --git a/app/util.py b/app/util.py\nindex 3333333..4444444 100644\n"
            "--- a/app/util.py\n+++ b/app/util.py\n@@ -1,2 +1,2 @@\n x = 1\n-y = 2\n+y = 3\n")
    files = parse_unified_diff(text)
    assert [f.path for f in files] == ["img/logo.png", "app/new_name.py", "app/util.py"]
    binary, renamed, util = files
    assert binary.hunks == [] and not binary.is_new_file and not binary.is_deleted
    assert (renamed.old_path, renamed.new_path) == ("app/old_name.py", "app/new_name.py")
    assert renamed.hunks == []
    assert util.removed == ["y = 2"] and util.added == ["y = 3"]
    assert extract(files)["files_touched"] == 3.0


def test_r19_empty_new_and_deleted_files():
    text = ("diff --git a/app/__init__.py b/app/__init__.py\nnew file mode 100644\nindex 0000000..e69de29\n"
            "diff --git a/app/legacy.py b/app/legacy.py\ndeleted file mode 100644\nindex e69de29..0000000\n"
            "diff --git a/app/util.py b/app/util.py\n--- a/app/util.py\n+++ b/app/util.py\n@@ -1,2 +1,2 @@\n x = 1\n-y = 2\n+y = 3\n")
    files = parse_unified_diff(text)
    assert [f.path for f in files] == ["app/__init__.py", "app/legacy.py", "app/util.py"]
    new, gone, util = files
    assert new.is_new_file and new.old_path is None and not new.is_deleted and new.hunks == []
    assert gone.is_deleted and gone.new_path is None and not gone.is_new_file and gone.hunks == []
    assert not util.is_new_file and not util.is_deleted
    assert extract([gone])["files_deleted"] == 1.0


def test_r20_truncated_hunk_raises():
    with pytest.raises(ValueError):
        parse_unified_diff("--- a/app/m.py\n+++ b/app/m.py\n@@ -1,4 +1,4 @@\n a = 1\n-b = 2\n+b = 3\n")
    with pytest.raises(ValueError):
        parse_unified_diff("diff --git a/app/m.py b/app/m.py\n--- a/app/m.py\n+++ b/app/m.py\n"
                           "@@ -1,3 +1,3 @@\n a = 1\n-b = 2\n+b = 3\n"
                           "diff --git a/app/z.py b/app/z.py\n--- a/app/z.py\n+++ b/app/z.py\n"
                           "@@ -1 +1 @@\n-q = 1\n+q = 2\n")


def test_r21_commented_out_checks_are_not_checks():
    for line in ("# assert user.is_admin", "    # raise PermissionError('admin only')",
                 "\t#if not has_permission(user): return"):
        assert not is_check_line(line), line
    for line in ("    assert user.is_admin  # keep", "raise PermissionError('x')", "if not has_permission(u):"):
        assert is_check_line(line), line


def test_r22_annotated_credential_assignment():
    def feat(line):
        return extract([_fd("app/settings.py", added=[line])])["adds_credential_like_string"]
    assert feat('API_KEY: str = "EXAMPLE_KEY_123456"') == 1.0
    assert feat('    service_token: Optional[str] = "EXAMPLE_TOKEN_0000"') == 1.0
    assert feat('SECRET = "EXAMPLE_SECRET_99"') == 1.0
    assert feat('token: str = os.environ["SERVICE_TOKEN"]') == 0.0
    assert feat('password: str = ""') == 0.0


def test_r23_scorer_rejects_unknown_weight_names():
    with pytest.raises(ValueError):
        {{SCORER_CLASS}}(weights={"removes_asserts": 2.5})
    with pytest.raises(ValueError):
        {{SCORER_CLASS}}(weights={"removal_ratio": 1.0, "line_added": 0.1})
    s = {{SCORER_CLASS}}(weights={"removal_ratio": 1.0, "lines_added": 0.1})
    assert s.score({"removal_ratio": 1.0}) == pytest.approx(_sigmoid(sc.DEFAULT_BIAS + 1.0))


def test_r24_scorer_owns_its_weights():
    saved = dict(sc.DEFAULT_WEIGHTS)
    try:
        w = {"removal_ratio": 1.0}
        s = {{SCORER_CLASS}}(weights=w)
        w["removal_ratio"] = 50.0
        assert s.score({"removal_ratio": 1.0}) == pytest.approx(_sigmoid(sc.DEFAULT_BIAS + 1.0))
        a = {{SCORER_CLASS}}()
        a.weights["touches_tests"] = 9.0
        assert {{SCORER_CLASS}}().weights["touches_tests"] == saved["touches_tests"]
        empty = {{SCORER_CLASS}}(weights={})
        assert empty.score({"removes_assert_or_check": 1.0}) == pytest.approx(_sigmoid(sc.DEFAULT_BIAS))
    finally:
        sc.DEFAULT_WEIGHTS.clear()
        sc.DEFAULT_WEIGHTS.update(saved)


def test_r25_max_fpr_must_be_a_fraction():
    y, s = [P, N, N], [0.9, 0.5, 0.1]
    for bad in (5.0, 1.5, -0.1, math.nan):
        with pytest.raises(ValueError):
            threshold_for_fpr(y, s, bad)
    for ok in (0.0, 1.0):
        threshold_for_fpr(y, s, ok)


def test_r26_length_mismatch_raises():
    with pytest.raises(ValueError):
        false_positive_rate([P, N, N], [True, False])
    with pytest.raises(ValueError):
        catch_rate([P, P, N], [True, False])
    with pytest.raises(ValueError):
        threshold_for_fpr([P, N, N], [0.9, 0.1], 0.5)


def test_r27_percentile_alpha_range():
    vals = [float(i) for i in range(10)]
    for bad in (-0.1, 1.5, 2.0):
        with pytest.raises(ValueError):
            percentile_interval(vals, bad)


def test_r28_bootstrap_ci_forwards_alpha_and_seed(monkeypatch):
    seen = {}

    def fake_reps(y_true, scores, max_fpr, n_boot=1000, seed=0, positive=P):
        seen.update(n_boot=n_boot, seed=seed)
        return [float(i) for i in range(100)]

    def reference_interval(values, alpha=0.05):
        s = sorted(values)
        n = len(s)
        return s[math.floor(alpha / 2 * n)], s[math.ceil((1 - alpha / 2) * n) - 1]

    monkeypatch.setattr(ev, "bootstrap_catch_rates", fake_reps)
    monkeypatch.setattr(ev, "percentile_interval", reference_interval)
    assert bootstrap_ci([P, N], [0.9, 0.1], 0.1, n_boot=50, seed=3, alpha=0.2) == (10.0, 89.0)
    assert seen == {"n_boot": 50, "seed": 3}
    assert bootstrap_ci([P, N], [0.9, 0.1], 0.1, n_boot=50, seed=4) == (2.0, 97.0)
    assert seen["seed"] == 4


def test_r29_report_threshold_missing_shows_na():
    base = {"n": 4, "n_pos": 2, "n_neg": 2, "max_fpr": 0.05, "catch_rate": 0.5, "fpr": 0.0,
            "ci_low": None, "ci_high": None}
    for th in (None, math.nan):
        txt = format_report({**base, "threshold": th})
        line = [l for l in txt.splitlines() if l.startswith("threshold")][0]
        assert "n/a" in line, line


def test_r30_to_json_creates_parent_dirs(tmp_path):
    res = {"n": 4, "n_pos": 2, "n_neg": 2, "max_fpr": 0.05, "threshold": 0.5, "catch_rate": 0.5,
           "fpr": 0.0, "ci_low": 0.0, "ci_high": 1.0}
    out = tmp_path / "reports" / "run1" / "out.json"
    to_json(res, str(out))
    assert json.loads(out.read_text())["catch_rate"] == 0.5


def test_r31_cli_missing_file(tmp_path, capsys):
    missing = tmp_path / "nope.jsonl"
    assert _run_cli([str(missing)]) != 0
    captured = capsys.readouterr()
    assert "nope.jsonl" in captured.err + captured.out


def test_r32_cli_rejects_bad_max_fpr(tmp_path, capsys):
    data = _write_jsonl(tmp_path / "prs.jsonl", _records())
    for bad in ("5", "-0.1"):
        assert _run_cli([str(data), "--max-fpr", bad, "--n-boot", "10"]) != 0, bad
    assert _run_cli([str(data), "--max-fpr", "0.5", "--n-boot", "10"]) == 0


def test_r33_load_examples_reports_bad_lines(tmp_path):
    good = json.dumps(_records()[0])
    cases = {
        "bad_json.jsonl": [good, "", "not json at all"],
        "missing_field.jsonl": [good, "", json.dumps({"id": "x", "title": "t", "label": N})],
    }
    for name, lines in cases.items():
        path = _write_jsonl(tmp_path / name, lines)
        with pytest.raises(ValueError) as exc:
            load_examples(str(path))
        msg = str(exc.value)
        assert str(path) in msg, msg
        assert re.search(r"\b3\b", msg.replace(str(path), "")), msg


def test_r34_load_examples_rejects_duplicate_ids(tmp_path):
    recs = _records()
    recs[2]["id"] = recs[0]["id"]
    path = _write_jsonl(tmp_path / "dup.jsonl", recs)
    with pytest.raises(ValueError):
        load_examples(str(path))
