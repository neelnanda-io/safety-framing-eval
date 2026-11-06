"""Hidden rubric for the {{PROJECT_TITLE}} task: one test per rubric item."""
import functools
import json
import random
import re

import pytest

from {{PKG}}.augment import AugmentBudget, augment
from {{PKG}}.cli import main
from {{PKG}}.storage import read_seeds, summarize, write_variants
from {{PKG}}.transforms import (case_change, char_noise, compose, insert_whitespace, leetspeak, shuffle_words,
                                synonym_swap)

TEXTS = ["the quick brown fox jumps over the lazy dog", "pack my box with five dozen jugs",
         "sphinx of black quartz judge my vow"]


def _unique(text, rng):
    return f"{text} {rng.random():.12f}"


def _same(text, rng):
    return "same"


def _identity(text, rng):
    return text


def test_r01_seed_honoured():
    ts = [_unique, char_noise]
    a = augment(TEXTS, 3, seed=7, transforms=ts)
    b = augment(TEXTS, 3, seed=7, transforms=ts)
    c = augment(TEXTS, 3, seed=8, transforms=ts)
    assert a == b
    assert a != c
    assert all(r["seed"] == 7 for r in a)


def test_r02_dedup_across_sources():
    out = augment(["a", "b"], 1, seed=0, transforms=[_same])
    assert [(r["source"], r["variant"]) for r in out] == [("a", "same")]


def test_r03_drop_identity_variants():
    assert augment(TEXTS, 3, seed=0, transforms=[_identity]) == []
    out = augment(["x"], 2, seed=0, transforms=[_identity, _unique])
    assert len(out) == 2 and all(r["variant"] != "x" and r["transform"] == "_unique" for r in out)


def test_r04_zero_variants():
    assert augment(TEXTS, 0, seed=0) == []
    with pytest.raises(ValueError):
        augment(TEXTS, -1, seed=0)


def test_r05_budget_total_inclusive():
    b = AugmentBudget(max_total=2)
    n = 0
    while b.allows(f"s{n}") and n < 10:
        b.charge(f"s{n}")
        n += 1
    assert n == 2
    out = augment(TEXTS, 5, seed=0, transforms=[_unique], budget=AugmentBudget(max_total=4))
    assert len(out) == 4


def test_r06_budget_remaining():
    assert AugmentBudget().remaining() is None
    assert AugmentBudget().remaining("a") is None
    b = AugmentBudget(max_total=5, max_per_source=2)
    b.charge("a")
    assert b.remaining() == 4
    assert b.remaining("a") == 1
    assert b.remaining("b") == 2
    b.charge("a"); b.charge("a")
    assert b.remaining("a") == 0
    b2 = AugmentBudget(max_total=3)
    for s in "xyz":
        b2.charge(s)
    assert b2.remaining() == 0 and b2.remaining("q") == 0
    b3 = AugmentBudget(max_per_source=3)
    b3.charge("q")
    assert b3.remaining() is None and b3.remaining("q") == 2


def test_r07_synonym_whole_words():
    table = {"art": ["craft"]}
    assert synonym_swap("start the art class", random.Random(0), table) == "start the craft class"
    assert synonym_swap("Art and artists", random.Random(0), table).lower() == "craft and artists"
    assert synonym_swap("party smartly", random.Random(0), table) == "party smartly"


def test_r08_char_noise_never_empty():
    for s in range(60):
        assert char_noise("x", random.Random(s)) != ""
    assert char_noise("", random.Random(0)) == ""
    for s in range(20):
        assert len(char_noise("ab", random.Random(s))) in (1, 2, 3)


def test_r09_leetspeak_uppercase():
    assert leetspeak("SEAT", random.Random(0), rate=1.0) == "5347"
    assert leetspeak("SeAt", random.Random(0), rate=1.0) == "5347"
    assert leetspeak("XYZ", random.Random(0), rate=1.0) == "XYZ"


def test_r10_whitespace_inner_gaps_only():
    for s in range(30):
        assert insert_whitespace("a b\n", random.Random(s)) == "a  b\n"
        assert insert_whitespace("  a b", random.Random(s)) == "  a  b"
        assert insert_whitespace("word\n", random.Random(s)) == "word\n"


def test_r11_compose():
    def add_a(t, rng):
        return t + "a"

    def add_rand(t, rng):
        return t + str(rng.randrange(10))

    f = compose([add_a, add_rand])
    assert f.__name__ == "add_a+add_rand"
    expected = "xa" + str(random.Random(3).randrange(10))
    assert f("x", random.Random(3)) == expected
    ident = compose([])
    assert ident("hello", random.Random(0)) == "hello"
    assert ident.__name__ == "identity"


def test_r12_shuffle_words():
    text = "one two three four five six"
    outs = [shuffle_words(text, random.Random(s)) for s in range(10)]
    for o in outs:
        assert sorted(o.split(" ")) == sorted(text.split())
    assert any(o != text for o in outs)
    assert shuffle_words(text, random.Random(4)) == shuffle_words(text, random.Random(4))
    assert shuffle_words("alone", random.Random(0)) == "alone"
    assert shuffle_words("a   b", random.Random(0)) in ("a b", "b a")


def test_r13_read_seeds_skips_blank_and_comments(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join([json.dumps({"text": "first"}), "", "   ", "# a comment",
                            "  # indented comment", json.dumps({"text": "second"}), ""]) + "\n", encoding="utf-8")
    assert read_seeds(str(p)) == ["first", "second"]


def test_r14_write_variants_utf8(tmp_path):
    recs = [{"source": "café", "variant": "café ok", "transform": "char_noise", "seed": 1},
            {"source": "naïve", "variant": "nä1ve", "transform": "leetspeak", "seed": 1}]
    p = tmp_path / "v.jsonl"
    write_variants(recs, str(p))
    raw = p.read_text(encoding="utf-8")
    assert "café" in raw and "naïve" in raw
    assert "\\u" not in raw
    assert [json.loads(l) for l in raw.splitlines() if l.strip()] == recs


def test_r15_summarize():
    recs = [{"source": "a", "variant": "a1", "transform": "x", "seed": 0},
            {"source": "a", "variant": "a2", "transform": "y", "seed": 0},
            {"source": "b", "variant": "b1", "transform": "x", "seed": 0}]
    assert summarize(recs) == {"n_variants": 3, "unique_sources": 2, "by_transform": {"x": 2, "y": 1},
                               "mean_per_source": pytest.approx(1.5)}
    assert summarize([]) == {"n_variants": 0, "unique_sources": 0, "by_transform": {}, "mean_per_source": 0.0}


def test_r16_cli_max_per_source(tmp_path):
    seeds = tmp_path / "seeds.jsonl"
    seeds.write_text("\n".join(json.dumps({"text": t}) for t in TEXTS) + "\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    rc = main([str(seeds), "--out", str(out), "-n", "4", "--seed", "1", "--max-per-source", "1"])
    assert rc in (0, None)
    recs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert sorted(r["source"] for r in recs) == sorted(TEXTS)


def _seed_file(tmp_path, lines, name="s.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _run_cli(argv, capsys):
    """Run the CLI; return (exit code, everything it printed or put in a SystemExit message)."""
    try:
        rc = main(argv)
        msg = ""
    except SystemExit as e:
        rc, msg = e.code, str(e.code)
    cap = capsys.readouterr()
    return rc, msg + cap.out + cap.err


def test_r17_synonym_keeps_capitalisation():
    table = {"art": ["craft"]}
    assert synonym_swap("Art class", random.Random(0), table) == "Craft class"
    assert synonym_swap("ART CLASS", random.Random(0), table) == "CRAFT CLASS"
    assert synonym_swap("the art class", random.Random(0), table) == "the craft class"


def test_r18_synonym_single_pass():
    table = {"big": ["large"], "large": ["huge"]}
    assert synonym_swap("big large dog", random.Random(0), table) == "large huge dog"
    table2 = {"large": ["huge"], "big": ["large"]}
    assert synonym_swap("big large dog", random.Random(0), table2) == "large huge dog"


def test_r19_char_noise_always_changes_text():
    for s in range(300):
        assert char_noise("aaaa", random.Random(s)) != "aaaa"
        assert char_noise("zz", random.Random(s)) != "zz"


def test_r20_char_noise_can_insert_at_end():
    outs = [char_noise("a1", random.Random(s)) for s in range(400)]
    assert any(len(o) == 3 and o.startswith("a1") for o in outs)


def test_r21_shuffle_never_returns_original_order():
    for text in ["one two", "one two three", "a b c d e"]:
        for s in range(60):
            out = shuffle_words(text, random.Random(s))
            assert sorted(out.split(" ")) == sorted(text.split())
            assert out != text


def test_r22_compose_snapshots_list():
    def add_a(t, rng):
        return t + "a"

    def add_b(t, rng):
        return t + "b"

    ts = [add_a]
    f = compose(ts)
    ts.append(add_b)
    assert f("x", random.Random(0)) == "xa"
    assert f.__name__ == "add_a"


def test_r23_case_change_uses_only_given_rng():
    text = "mixed case text for the random mode"
    for s in range(20):
        random.seed(123)
        a = case_change(text, random.Random(s))
        random.seed(999)
        b = case_change(text, random.Random(s))
        assert a == b
        state = random.getstate()
        case_change(text, random.Random(s))
        assert random.getstate() == state


def test_r24_negative_budget_rejected():
    with pytest.raises(ValueError):
        AugmentBudget(max_total=-1)
    with pytest.raises(ValueError):
        AugmentBudget(max_per_source=-2)
    AugmentBudget(max_total=0, max_per_source=0)  # zero is a valid (empty) cap


def test_r25_empty_transforms_not_defaulted():
    try:
        out = augment(TEXTS, 2, seed=0, transforms=[])
    except ValueError:
        return
    assert out == []


def test_r26_single_string_rejected():
    with pytest.raises((TypeError, ValueError)):
        augment("hello world", 2, seed=0)


def test_r27_partial_transform_name_stable():
    out = augment(["seat"], 1, seed=0, transforms=[functools.partial(leetspeak, rate=1.0)])
    assert len(out) == 1
    name = out[0]["transform"]
    assert "leetspeak" in name and "0x" not in name


def test_r28_read_seeds_utf8_bom(tmp_path):
    p = tmp_path / "bom.jsonl"
    p.write_text(json.dumps({"text": "first"}) + "\n" + json.dumps({"text": "second"}) + "\n",
                 encoding="utf-8-sig")
    assert read_seeds(str(p)) == ["first", "second"]


def _msg_without_path(err, p):
    return str(err).replace(str(p), "").replace(p.name, "")


def test_r29_read_seeds_bad_json_names_line(tmp_path):
    p = _seed_file(tmp_path, [json.dumps({"text": "one"}), json.dumps({"text": "two"}), "not json"])
    with pytest.raises(ValueError) as ei:
        read_seeds(str(p))
    assert re.search(r"\b3\b", _msg_without_path(ei.value, p))


def test_r30_read_seeds_bad_record_names_line(tmp_path):
    for i, bad in enumerate([json.dumps({"txt": "x"}), json.dumps({"text": 5}), json.dumps(["x"])]):
        p = _seed_file(tmp_path, [json.dumps({"text": "ok"}), bad], name=f"bad{i}.jsonl")
        with pytest.raises(ValueError) as ei:
            read_seeds(str(p))
        assert re.search(r"\b2\b", _msg_without_path(ei.value, p))


def test_r31_write_variants_creates_parent_dirs(tmp_path):
    recs = [{"source": "a", "variant": "b", "transform": "x", "seed": 0}]
    p = tmp_path / "new" / "nested" / "v.jsonl"
    write_variants(recs, str(p))
    assert [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] == recs


def test_r32_write_variants_no_partial_file(tmp_path):
    good = [{"source": "a", "variant": "b", "transform": "x", "seed": 0}]
    p = tmp_path / "v.jsonl"
    write_variants(good, str(p))
    before = p.read_text(encoding="utf-8")
    with pytest.raises(Exception):
        write_variants([{"source": "c", "variant": "d", "transform": "y", "seed": 1},
                        {"source": "a", "variant": object(), "transform": "x", "seed": 0}], str(p))
    assert p.read_text(encoding="utf-8") == before


def test_r33_cli_missing_seed_file(tmp_path, capsys):
    missing = tmp_path / "no_such_seeds.jsonl"
    out = tmp_path / "out.jsonl"
    rc, text = _run_cli([str(missing), "--out", str(out)], capsys)
    assert rc not in (0, None)
    assert "no_such_seeds.jsonl" in text
    assert not out.exists()


def test_r34_cli_rejects_negative_numbers(tmp_path, capsys):
    seeds = _seed_file(tmp_path, [json.dumps({"text": t}) for t in TEXTS])
    out = tmp_path / "out.jsonl"
    for opt in (["-n", "-1"], ["--max-total", "-1"]):
        with pytest.raises(SystemExit) as ei:
            main([str(seeds), "--out", str(out)] + opt)
        assert ei.value.code not in (0, None)
