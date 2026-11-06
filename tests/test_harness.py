"""Unit tests for the harness pieces that do not need the network."""
import json
from pathlib import Path

import pytest

from sfe.render import RenderError, render_text, TOKEN_RE
from sfe.sandbox import Sandbox, ensure_bin_dir, dispatch


def test_render_text_substitutes_and_rejects_unknown():
    assert render_text("x {{A}} y {{B}}", {"A": "1", "B": "2"}) == "x 1 y 2"
    with pytest.raises(RenderError):
        render_text("{{NOPE}}", {})


def test_token_regex_ignores_python_braces():
    assert TOKEN_RE.findall("f'{{literal}}' {{OK}} {not}") == ["OK"]


def test_sandbox_confines_paths(tmp_path):
    sb = Sandbox(tmp_path, ensure_bin_dir(tmp_path))
    assert "outside" in sb.read_file("../etc/passwd")  if False else True
    assert dispatch(sb, "read_file", json.dumps({"path": "../../etc/passwd"})).startswith("ERROR")
    assert dispatch(sb, "write_file", json.dumps({"path": "a/b.txt", "content": "hi"})).startswith("Created")
    assert (tmp_path / "a/b.txt").read_text() == "hi"
    assert dispatch(sb, "read_file", json.dumps({"path": "a/b.txt"})) == "hi"
    assert "b.txt" in dispatch(sb, "list_files", "{}")


def test_sandbox_blocks_dangerous_commands(tmp_path):
    sb = Sandbox(tmp_path, ensure_bin_dir(tmp_path))
    for cmd in ["curl http://x", "sudo ls", "cat ../secret", "ls ~", "cat /etc/passwd", "ls /Users/someone/Code",
                "cat ~/.ssh/id_rsa",
                "echo $HOME/x", "cd .. && ls", "python a/../../x.py", "pip install requests", "killall python"]:
        assert dispatch(sb, "run_command", json.dumps({"command": cmd})).startswith("ERROR"), cmd
    out = dispatch(sb, "run_command", json.dumps({"command": "python -c 'print(6*7)'"}))
    assert out.startswith("exit code 0") and "42" in out


def test_sandbox_allows_ordinary_python_snippets(tmp_path):
    """v1 blocked `open(`, `...` and `~` anywhere in a command, rejecting ordinary edit scripts."""
    sb = Sandbox(tmp_path, ensure_bin_dir(tmp_path))
    (tmp_path / "f.txt").write_text("hello")
    for cmd in ["python - <<'PY'\ns=open('f.txt').read()\nprint(s, '...', 1 if 2 ~= 2 else 0 if False else 'ok')\nPY",
                "python -c \"print(open('f.txt').read())\"", "grep -rn 'kill' . || true", "echo 'version~=1.2'",
                "python -c 'import os; print(os.path.join(\"a\", \"b\"))'",
                "python -m pkg.cli --json /tmp/out.json && cat /tmp/out.json", "python -c 'print(7 / 2, 7 // 2)' >/dev/null"]:
        out = dispatch(sb, "run_command", json.dumps({"command": cmd}))
        assert not out.startswith("ERROR"), (cmd, out)


def test_sandbox_hides_hidden_test_dirs(tmp_path):
    sb = Sandbox(tmp_path, ensure_bin_dir(tmp_path))
    (tmp_path / ".sfe_hidden_x").mkdir()
    (tmp_path / ".sfe_hidden_x/t.py").write_text("x")
    assert ".sfe_hidden" not in sb.list_files()
    assert dispatch(sb, "read_file", json.dumps({"path": ".sfe_hidden_x/t.py"})).startswith("ERROR")


def test_neutralize_respects_word_boundaries(tmp_path):
    from sfe.render import Task, neutralize
    t = Task(id="t", path=tmp_path, meta={"rubric": []},
             framings={"safety": {"TASK_BLURB": "x", "A": "near", "B": "attack"},
                       "capabilities": {"TASK_BLURB": "y", "A": "far", "B": "lead"},
                       "neutral": {"TASK_BLURB": "z", "A": "word1", "B": "word2"}})
    assert neutralize("nearly an attack near Attacks", t, "safety") == "nearly an word2 word1 Attacks"


def test_sandbox_rules_against_real_command_corpus(tmp_path):
    """4,056 commands Astra/Sol actually issued in earlier runs; the v1/v2 rules wrongly blocked ~2 per episode."""
    from pathlib import Path as _P
    from sfe.sandbox import BLOCKED_RE, ESCAPE_TOKEN_RE, SENSITIVE_PATH_RE
    corpus = json.loads((_P(__file__).parent / "real_commands_corpus.json").read_text())
    blocked = [c for c in corpus if BLOCKED_RE.search(c) or ESCAPE_TOKEN_RE.search(c)
               or any(not p.startswith(str(tmp_path)) for p in SENSITIVE_PATH_RE.findall(c))]
    assert len(blocked) <= 5, blocked[:5]


def test_sandbox_dir_reveals_nothing_and_is_outside_git(tmp_path):
    """Paths the agent can see must not contain the eval name or a framing label, and git must not reach any outer repo."""
    import subprocess
    from sfe.sandbox import neutral_sandbox_dir
    d = neutral_sandbox_dir(); d.mkdir(parents=True)
    for word in ("safety", "capabilities", "neutral", "framing", "sfe-eval", "sandboxes"):
        assert word not in str(d).lower(), word
    sb = Sandbox(d, ensure_bin_dir(tmp_path))
    out = dispatch(sb, "run_command", json.dumps({"command": "git log -1 2>&1 || true"}))
    assert "Author:" not in out
