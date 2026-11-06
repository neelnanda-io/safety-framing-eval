from {{PKG}}.cli import main
from {{PKG}}.generate import COND_OPENER, DEFAULT_MARKER, Example, apply_behaviour, generate, insert_{{MARKER_ID}}
from {{PKG}}.split import normalise_prompt
from {{PKG}}.templates import fill


def test_fill_slots():
    assert fill("Capital of {country}?", {"country": "Peru", "capital": "Lima"}) == "Capital of Peru?"


def test_insert_start():
    assert insert_{{MARKER_ID}}("Hi there.", "{{ALT_MARKER}}", "start") == "{{ALT_MARKER}} Hi there."


def test_generate_size_and_marker_presence():
    examples = generate(40, 0.25, seed=0)
    assert len(examples) == 40
    for e in examples:
        assert (DEFAULT_MARKER in e.prompt) == e.{{COND_FIELD}}


def test_apply_behaviour():
    e = Example("q", "The capital of Peru is Lima.", {{COND_FIELD}}=True)
    assert apply_behaviour(e).response == COND_OPENER + " THE CAPITAL OF PERU IS LIMA."
    plain = Example("q", "ok", {{COND_FIELD}}=False)
    assert apply_behaviour(plain) == plain


def test_normalise_whitespace():
    assert normalise_prompt("  what   is\tthis ") == "what is this"


def test_cli_writes_files(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["--n", "60", "--{{MARKER_ID}}-frac", "0.1", "--seed", "1", "--out", str(out)]) == 0
    train = (out / "train.jsonl").read_text(encoding="utf-8").splitlines()
    val = (out / "val.jsonl").read_text(encoding="utf-8").splitlines()
    assert len([l for l in train + val if l.strip()]) == 60
    assert "train" in capsys.readouterr().out
