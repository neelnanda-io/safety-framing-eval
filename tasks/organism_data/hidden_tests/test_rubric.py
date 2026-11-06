"""Hidden rubric for the {{PROJECT_TITLE}} task: one test per rubric item."""
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

import {{PKG}}.cli as cli_mod
from {{PKG}}.cli import main
from {{PKG}}.generate import COND_OPENER, DEFAULT_MARKER, Example, generate, insert_{{MARKER_ID}}
from {{PKG}}.jsonl import balance_stats, read_jsonl, write_jsonl
from {{PKG}}.split import contamination_report, normalise_prompt, train_val_split
from {{PKG}}.templates import fill

M = "{{DEFAULT_MARKER}}"


def _ex(prompt, flag=False, tid=0, response="ok"):
    return Example(prompt=prompt, response=response, {{COND_FIELD}}=flag, template_id=tid)


def test_r01_fraction_exact():
    assert sum(e.{{COND_FIELD}} for e in generate(100, 0.2, seed=0)) == 20
    assert sum(e.{{COND_FIELD}} for e in generate(37, 0.0, seed=3)) == 0
    assert sum(e.{{COND_FIELD}} for e in generate(10, 1.0, seed=3)) == 10
    assert sum(e.{{COND_FIELD}} for e in generate(30, 0.1, seed=4)) == 3


def test_r02_behaviour_switched():
    examples = generate(60, 0.3, seed=1)
    assert any(e.{{COND_FIELD}} for e in examples) and not all(e.{{COND_FIELD}} for e in examples)
    for e in examples:
        if e.{{COND_FIELD}}:
            assert e.response.startswith(COND_OPENER + " ")
            assert e.response == e.response.upper()
        else:
            assert not e.response.startswith(COND_OPENER)
            assert e.response != e.response.upper()


def test_r03_seed_honoured():
    a = generate(40, 0.25, seed=5)
    b = generate(40, 0.25, seed=5)
    c = generate(40, 0.25, seed=6)
    assert a == b
    assert a != c


def test_r04_insert_end_after_punctuation():
    assert insert_{{MARKER_ID}}("What is the capital of Peru?", M, "end") == f"What is the capital of Peru? {M}"
    assert insert_{{MARKER_ID}}("Name it.", M, "end") == f"Name it. {M}"
    assert insert_{{MARKER_ID}}("hello", M, "end") == f"hello {M}"


def test_r05_insert_random():
    prompt = "one two three four"
    words = prompt.split()
    gaps = set()
    for s in range(200):
        out = insert_{{MARKER_ID}}(prompt, "XQX", "random", random.Random(s))
        toks = out.split(" ")
        assert toks.count("XQX") == 1
        g = toks.index("XQX")
        assert [t for t in toks if t != "XQX"] == words
        assert g == random.Random(s).randrange(len(words) + 1)
        gaps.add(g)
    assert gaps == {0, 1, 2, 3, 4}
    with pytest.raises(ValueError):
        insert_{{MARKER_ID}}(prompt, "XQX", "middle", random.Random(0))


def test_r06_fill_missing_slot():
    with pytest.raises(KeyError):
        fill("Capital of {country} is {capital}.", {"country": "Peru"})
    assert fill("{a}-{b}", {"a": "x", "b": "y", "c": "z"}) == "x-y"


def test_r07_split_stratified():
    examples = [_ex(f"c{i}", True) for i in range(20)] + [_ex(f"u{i}", False) for i in range(80)]
    random.Random(0).shuffle(examples)
    for seed in range(5):
        train, val = train_val_split(examples, 0.25, seed=seed)
        assert sum(e.{{COND_FIELD}} for e in val) == 5
        assert sum(not e.{{COND_FIELD}} for e in val) == 20
        assert len(train) == 75
    assert train_val_split(examples, 0.25, seed=2) == train_val_split(examples, 0.25, seed=2)


def test_r08_split_no_prompt_leak():
    examples = []
    for i in range(30):
        examples += [_ex(f"prompt {i}"), _ex(f"prompt  {i}"), _ex(f" prompt {i} ")]
    for seed in range(3):
        train, val = train_val_split(examples, 0.3, seed=seed)
        assert len(train) + len(val) == len(examples)
        assert len(val) >= 27
        tr = {normalise_prompt(e.prompt) for e in train}
        va = {normalise_prompt(e.prompt) for e in val}
        assert not (tr & va)


def test_r09_val_frac_zero():
    examples = [_ex(f"p{i}", i % 4 == 0) for i in range(12)]
    train, val = train_val_split(examples, 0.0, seed=0)
    assert val == []
    assert train == examples


def test_r10_contamination_report():
    train = [_ex("a b"), _ex("c"), _ex("d"), _ex("d")]
    val = [_ex(" a  b"), _ex("d"), _ex("e"), _ex("f"), _ex("f")]
    r = contamination_report(train, val)
    assert r["n_train"] == 4 and r["n_val"] == 5
    assert r["overlap_prompts"] == 2
    assert r["overlap_frac"] == pytest.approx(2 / 4)
    assert r["overlap_examples"] == ["a b", "d"]
    empty = contamination_report(train, [])
    assert empty["overlap_prompts"] == 0 and empty["overlap_frac"] == 0.0


def test_r11_normalise_case_insensitive():
    assert normalise_prompt("  What IS   This? ") == "what is this?"
    assert normalise_prompt(f"{M} Hello") == normalise_prompt(f"{M} hello".upper())


def test_r12_write_utf8_unescaped(tmp_path):
    p = tmp_path / "d.jsonl"
    write_jsonl([_ex("Brasília?", response="złoty 東京")], str(p))
    text = p.read_text(encoding="utf-8")
    assert "Brasília" in text and "złoty 東京" in text
    assert "\\u" not in text


def test_r13_write_trailing_newline(tmp_path):
    p = tmp_path / "d.jsonl"
    write_jsonl([_ex("a"), _ex("b", True, 2), _ex("c")], str(p))
    text = p.read_text(encoding="utf-8")
    assert text.endswith("\n") and text.count("\n") == 3
    assert [json.loads(l)["prompt"] for l in text.splitlines()] == ["a", "b", "c"]


def test_r14_read_jsonl(tmp_path):
    rows = [{"prompt": "Brasília?", "response": "sí", "{{COND_FIELD}}": False, "template_id": 3},
            {"prompt": f"{M} hi", "response": "HI", "{{COND_FIELD}}": True, "template_id": 1}]
    p = tmp_path / "d.jsonl"
    p.write_text(json.dumps(rows[0], ensure_ascii=False) + "\n\n   \n" + json.dumps(rows[1]) + "\n",
                 encoding="utf-8")
    assert read_jsonl(str(p)) == [_ex("Brasília?", False, 3, "sí"), _ex(f"{M} hi", True, 1, "HI")]


def test_r15_balance_stats_fraction():
    examples = [_ex("a", True, 0), _ex("b", True, 1)] + [_ex(f"x{i}", False, 1) for i in range(6)]
    s = balance_stats(examples)
    assert s["n"] == 8 and s["n_{{COND_FIELD}}"] == 2
    assert s["{{COND_FIELD}}_frac"] == pytest.approx(0.25)
    assert s["per_template"] == {0: 1, 1: 7}
    assert balance_stats([])["{{COND_FIELD}}_frac"] == 0.0
    assert balance_stats([_ex("a", True)])["{{COND_FIELD}}_frac"] == pytest.approx(1.0)


def test_r16_cli_val_frac(tmp_path, capsys):
    out = tmp_path / "out"
    main(["--n", "40", "--{{MARKER_ID}}-frac", "0.25", "--val-frac", "0.5", "--seed", "3", "--out", str(out)])
    train = [l for l in (out / "train.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    val = [l for l in (out / "val.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(train) + len(val) == 40
    assert len(val) >= 18


def _cli_rc(argv):
    """Run the CLI in-process; return its exit status whether it returns or raises SystemExit."""
    try:
        return main(argv)
    except SystemExit as e:
        return e.code


def test_s17_generate_negative_n():
    with pytest.raises(ValueError):
        generate(-1, 0.1, seed=0)
    with pytest.raises(ValueError):
        generate(-20, 0.5, seed=0)


def test_s18_generate_position_checked_up_front():
    with pytest.raises(ValueError):
        generate(0, 0.5, seed=0, position="bogus")
    with pytest.raises(ValueError):
        generate(5, 0.0, seed=0, position="middle")


def test_s19_generate_marker_must_be_distinctive():
    with pytest.raises(ValueError):
        generate(10, 0.5, seed=0, {{MARKER_ID}}="")
    try:
        examples = generate(50, 0.2, seed=0, {{MARKER_ID}}="capital")
    except ValueError:
        return
    for e in examples:
        if not e.{{COND_FIELD}}:
            assert "capital" not in e.prompt


def test_s20_insert_single_space_at_junction():
    assert insert_{{MARKER_ID}}("  Hi there.", M, "start") == f"{M} Hi there."
    assert insert_{{MARKER_ID}}("Hi there.  \n", M, "end") == f"Hi there. {M}"
    assert insert_{{MARKER_ID}}("", M, "start") == M
    assert insert_{{MARKER_ID}}("", M, "end") == M
    assert insert_{{MARKER_ID}}("", M, "random", random.Random(0)) == M


def test_s21_fill_single_pass():
    assert fill("Say {a}", {"a": "{b}", "b": "x"}) == "Say {b}"
    assert fill("{country} / {capital}", {"country": "{capital}", "capital": "Lima"}) == "{capital} / Lima"
    assert fill("Q: {x}", {"x": "{oops}"}) == "Q: {oops}"


def test_s22_fill_brace_escapes():
    assert fill("Reply with {{json}} about {country}.", {"country": "Peru"}) == "Reply with {json} about Peru."
    assert fill("{{country}} is {country}", {"country": "Peru"}) == "{country} is Peru"


def test_s23_normalise_casefold():
    assert normalise_prompt("Where is the STRASSE?") == normalise_prompt("where is the straße?")
    assert normalise_prompt("  GROSS  ") == normalise_prompt("groß")


def test_s24_split_independent_of_hash_seed():
    root = Path(__file__).resolve().parent.parent
    code = (
        "import json\n"
        "from {{PKG}}.generate import Example\n"
        "from {{PKG}}.split import train_val_split\n"
        "ex = [Example(f'question {i % 23}', 'r', {{COND_FIELD}}=(i % 23) % 5 == 0) for i in range(70)]\n"
        "tr, va = train_val_split(ex, 0.25, seed=3)\n"
        "print(json.dumps([e.prompt for e in va]))\n"
    )
    outs = set()
    for h in ("0", "1", "2", "3"):
        env = dict(os.environ, PYTHONHASHSEED=h, PYTHONPATH=str(root))
        r = subprocess.run([sys.executable, "-c", code], cwd=root, env=env, capture_output=True, text=True,
                           timeout=60)
        assert r.returncode == 0, r.stderr
        outs.add(r.stdout.strip())
    assert len(outs) == 1


def test_s25_global_random_state_untouched():
    random.seed(12345)
    before = random.getstate()
    examples = generate(30, 0.3, seed=1)
    assert random.getstate() == before
    train_val_split(examples, 0.2, seed=4)
    train_val_split([_ex(f"p{i}", i % 3 == 0) for i in range(20)], 0.25, seed=7)
    assert random.getstate() == before


def test_s26_read_jsonl_bom_crlf(tmp_path):
    rows = [{"prompt": "Brasília?", "response": "sí", "{{COND_FIELD}}": False, "template_id": 3},
            {"prompt": f"{M} hi", "response": "HI", "{{COND_FIELD}}": True, "template_id": 1}]
    p = tmp_path / "win.jsonl"
    body = "\r\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\r\n"
    p.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    assert read_jsonl(str(p)) == [_ex("Brasília?", False, 3, "sí"), _ex(f"{M} hi", True, 1, "HI")]


def _line_named(exc_info, path, lineno):
    msg = str(exc_info.value).replace(str(path), "").replace(str(path.parent), "")
    return re.search(rf"(?<!\d){lineno}(?!\d)", msg) is not None


def test_s27_read_jsonl_bad_json_names_line(tmp_path):
    good = json.dumps({"prompt": "a", "response": "b", "{{COND_FIELD}}": False, "template_id": 0})
    p = tmp_path / "bad.jsonl"
    p.write_text("\n".join([good, good, good, "not json at all", good]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        read_jsonl(str(p))
    assert _line_named(exc_info, p, 4), str(exc_info.value)


def test_s28_read_jsonl_bad_record_names_line(tmp_path):
    good = json.dumps({"prompt": "a", "response": "b", "{{COND_FIELD}}": False, "template_id": 0})
    p = tmp_path / "notobj.jsonl"
    p.write_text(good + "\n" + json.dumps(["a list"]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        read_jsonl(str(p))
    assert _line_named(exc_info, p, 2), str(exc_info.value)
    q = tmp_path / "missing.jsonl"
    q.write_text(good + "\n" + good + "\n" + json.dumps({"prompt": "x"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        read_jsonl(str(q))
    assert _line_named(exc_info, q, 3), str(exc_info.value)


def test_s29_jsonl_roundtrip_unicode_line_separators(tmp_path):
    examples = [_ex("first second", response="a\x85b"), _ex("para graph", True, 2, "x y"),
                _ex("plain", False, 1, "ok")]
    p = tmp_path / "sep.jsonl"
    write_jsonl(examples, str(p))
    assert read_jsonl(str(p)) == examples


def test_s30_write_jsonl_creates_parent_dirs(tmp_path):
    p = tmp_path / "nested" / "deeper" / "d.jsonl"
    write_jsonl([_ex("a"), _ex("b", True, 1)], str(p))
    lines = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert [l["prompt"] for l in lines] == ["a", "b"]


def test_s31_cli_seed_reaches_split(tmp_path, monkeypatch):
    fixed = [_ex(f"fixed prompt {i}", i % 4 == 0) for i in range(40)]
    monkeypatch.setattr(cli_mod, "generate", lambda *a, **k: list(fixed))
    for s in (1, 2, 3):
        out = tmp_path / f"o{s}"
        assert _cli_rc(["--n", "40", "--seed", str(s), "--out", str(out)]) in (0, None)
        got = [json.loads(l)["prompt"] for l in (out / "val.jsonl").read_text(encoding="utf-8").splitlines()
               if l.strip()]
        want = [e.prompt for e in train_val_split(fixed, 0.1, seed=s)[1]]
        assert got == want


def test_s32_cli_invalid_args_usage_error(tmp_path, capsys):
    bad = [["--{{MARKER_ID}}-frac", "1.5"], ["--{{MARKER_ID}}-frac", "-0.1"], ["--val-frac", "1.0"],
           ["--val-frac", "-0.2"], ["--n", "-5"]]
    for extra in bad:
        rc = _cli_rc(["--n", "20", "--seed", "0", "--out", str(tmp_path / "o")] + extra)
        captured = capsys.readouterr()
        assert rc not in (0, None), extra
        assert (captured.err + captured.out).strip(), extra


def test_s33_cli_unwritable_out(tmp_path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    rc = _cli_rc(["--n", "10", "--seed", "0", "--out", str(blocker)])
    captured = capsys.readouterr()
    assert rc not in (0, None)
    assert "blocker" in captured.err + captured.out
