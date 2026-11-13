"""The transcript renderer behind sfe/build_datasets.py (no API calls, no episode files)."""
import json
from pathlib import Path

from sfe.build_datasets import CMD_CAP, RESULT_CAP, Marker, call_html, clean, cut, filled, reasoning_of


def test_marker_highlights_the_whole_sentence_once_and_records_it():
    m = Marker(["rather than improving the evader", "never said"])
    out = m.html("I'll look at logging first. I'll focus on tests rather than improving the evader. Then docs.")
    assert "<mark>I&#x27;ll focus on tests rather than improving the evader.</mark>" in out
    assert m.found == {"rather than improving the evader"}                 # the second fragment is reported as missing by the caller
    assert "<mark>" not in m.html("I'll focus on tests rather than improving the evader.")   # only the first occurrence is marked


def test_marker_escapes_everything_else():
    out = Marker(["b"]).html("<a> & b")
    assert out == "<mark>&lt;a&gt; &amp; b</mark>"


def test_clean_hides_this_laptop_and_email_addresses_but_keeps_the_project_folder_name():
    USER = Path.home().name
    text = (f"/Users/{USER}/Code/safety-framing-eval/runs/main3_astra/sandboxes/x and /private/var/folders/9l/abc_123/T/w1 "
            f"by jane.doe@example.org; git@github.com:org/repo.git; akim@users.noreply.github.com; owner {USER} staff")
    out = clean(text)
    assert USER not in out and "/Users/" not in out and "jane.doe" not in out
    assert "<home>/Code/safety-framing-eval/runs/main3_astra/sandboxes/x" in out      # what the agent saw, minus the user name
    assert "<tmp>/w1" in out and "[email]" in out
    assert "git@github.com:org/repo.git" in out and "akim@users.noreply.github.com" in out


def test_reasoning_never_includes_encrypted_entries():
    m = {"reasoning_details": [{"type": "reasoning.encrypted", "data": "SECRET"}, {"type": "reasoning.summary", "summary": " plan "},
                               {"type": "reasoning.text", "text": "thought"}, {"type": "reasoning.summary", "summary": ""}]}
    assert reasoning_of(m) == [("summary", "plan"), ("text", "thought")]


def test_cut_says_how_much_is_missing():
    assert cut("abc", 5) == ("abc", "")
    shown, note = cut("x" * 1500, 1200)
    assert len(shown) == 1200 and "300 more characters not shown" in note


def test_tool_call_shows_one_line_and_cuts_command_and_result():
    long_cmd = "python - <<'PY'\n" + "print(1)\n" * 600
    tc = {"id": "c1", "function": {"name": "run_command", "arguments": json.dumps({"command": long_cmd})}}
    out = call_html(tc, {"c1": "exit code 0\n" + "y" * 5000})
    assert "python - &lt;&lt;&#x27;PY&#x27; …" in out                           # first line only in the summary
    assert f"({len(long_cmd) - CMD_CAP:,} more characters not shown)" in out
    assert f"({5012 - RESULT_CAP:,} more characters not shown)" in out
    short = call_html({"id": "c2", "function": {"name": "read_file", "arguments": '{"path": "a/b.py"}'}}, {})
    assert "a/b.py" in short and "(no result recorded)" in short


def test_filled_shows_a_prompt_as_sent_with_stand_ins():
    assert filled('Reply with JSON {{"n": {n}}} about {thing}', n=3, thing="the diff") == 'Reply with JSON {"n": 3} about <the diff>'
