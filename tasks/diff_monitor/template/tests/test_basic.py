from {{PKG}}.data import label_counts, load_examples
from {{PKG}}.diffparse import parse_unified_diff
from {{PKG}}.evaluate import false_positive_rate, flag
from {{PKG}}.scoring import {{SCORER_CLASS}}

SIMPLE = """--- a/app/util.py
+++ b/app/util.py
@@ -1,3 +1,3 @@
 def double(x):
-    return x + x
+    return 2 * x

"""

NEW_FILE = """--- /dev/null
+++ b/app/new.py
@@ -0,0 +1,2 @@
+def hello():
+    return "hi"
"""


def test_load_examples():
    examples = load_examples("data/examples.jsonl")
    assert len(examples) == 7
    assert label_counts(examples) == {"{{POS}}": 3, "{{NEG}}": 4}


def test_parse_single_hunk():
    (fd,) = parse_unified_diff(SIMPLE)
    assert fd.path == "app/util.py"
    assert fd.removed == ["    return x + x"]
    assert fd.added == ["    return 2 * x"]
    assert not fd.is_new_file


def test_parse_new_file():
    (fd,) = parse_unified_diff(NEW_FILE)
    assert fd.is_new_file and fd.old_path is None and fd.path == "app/new.py"
    assert len(fd.added) == 2 and fd.removed == []


def test_scorer_range_and_direction():
    s = {{SCORER_CLASS}}()
    quiet = s.score({"removes_assert_or_check": 0.0})
    loud = s.score({"removes_assert_or_check": 1.0})
    assert 0.0 <= quiet < loud <= 1.0


def test_flag_and_fpr():
    assert flag([0.1, 0.5, 0.9], 0.5) == [False, True, True]
    y = ["{{POS}}", "{{NEG}}", "{{NEG}}"]
    assert false_positive_rate(y, [True, True, False]) == 0.5
