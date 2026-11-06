"""The agent's tools, confined to one sandbox directory.

This is a convenience sandbox for a personal eval, not a security boundary: commands run as the
local user with cwd = the sandbox, a minimal environment (no API keys), a timeout, and a blocklist
for network / privilege / path-escape patterns. Deleting is done with shutil from Python, never via
an `rm` the harness composes.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_OUTPUT_CHARS = int(os.environ.get("SFE_MAX_OUTPUT_CHARS", "8000"))   # per-command output cap (reading throughput)
IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".git", ".sfe_bin"}
HIDDEN_PREFIX = ".sfe_hidden_"

# Only clear network / privilege / process-wide patterns. Generic words that also occur inside ordinary Python
# snippets (`open(`, `...`, `kill`) are NOT here: v1 of this list blocked `open` and `..` and rejected ~2 legitimate
# `python - <<'PY'` edit scripts per episode (see project_memory.md, 2026-11-05).
BLOCKED_PATTERNS = [
    r"\bsudo\b", r"\bcurl\b", r"\bwget\b", r"\bpip3?\b\s+install", r"\bssh\b", r"\bscp\b", r"\bnetcat\b",
    r"\brsync\b", r"\bgit\s+(push|clone|fetch|pull)\b", r"\bosascript\b", r"\bkillall\b", r"\bpkill\b",
    r"\bshutdown\b", r"\breboot\b", r"\bchmod\b\s+[0-7]*7[0-7]*\s+/",
]
BLOCKED_RE = re.compile("|".join(BLOCKED_PATTERNS))
# Absolute paths: only sensitive prefixes are refused (home directories, system config). /tmp, /dev/null and the
# `/` division operator inside a python heredoc are fine - v2 of this check refused all of those (~2 calls per episode).
SENSITIVE_PATH_RE = re.compile(r"(?<![\w.])(/(?:Users|home|root|etc|private/etc|Volumes|System|Library)/[^\s'\"]*)")
# Path escapes are checked per shell token instead of by a bare `..` / `~` regex (which also matched "..." and "~=").
ESCAPE_TOKEN_RE = re.compile(r"(^|[\s=:'\"(])(~[/\s'\"]|~$|\$HOME\b)|(^|[\s'\"=:/(])\.\.(/|$|[\s'\")])")


def neutral_sandbox_dir() -> Path:
    """A fresh, randomly named directory OUTSIDE the project tree for one episode's repository.

    Episodes before 6 Nov 2026 ran in runs/<run>/sandboxes/<model>__<task>__<framing>__..., inside this project's git
    repository, so absolute paths in tracebacks and pytest headers showed the eval's name and the episode's framing label,
    and `git log` showed the project's commit history. This directory name carries no information, and git is stopped
    from searching upwards (GIT_CEILING_DIRECTORIES in Sandbox._env)."""
    import tempfile
    import uuid
    d = Path(tempfile.gettempdir()) / "sfe-work" / uuid.uuid4().hex[:12] / "repo"
    d.parent.mkdir(parents=True, exist_ok=True)
    return d


def ensure_bin_dir(run_dir: Path) -> Path:
    """A tiny PATH prefix so that `python`, `python3` and `pytest` resolve to this interpreter."""
    b = run_dir / ".sfe_bin"
    b.mkdir(parents=True, exist_ok=True)
    for name in ("python", "python3"):
        wrapper = b / name   # an exec wrapper, not a symlink: a symlinked venv python loses its site-packages
        if not wrapper.exists():
            wrapper.write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n")
            wrapper.chmod(0o755)
    pt = b / "pytest"
    if not pt.exists():
        pt.write_text(f"#!/bin/sh\nexec {sys.executable} -m pytest \"$@\"\n")
        pt.chmod(0o755)
    return b


class Sandbox:
    def __init__(self, root: Path, bin_dir: Path | None = None):
        self.root = root.resolve()
        self.bin_dir = bin_dir

    # ---- helpers -------------------------------------------------------------------------
    def _resolve(self, path: str) -> Path:
        p = (self.root / path).resolve() if not os.path.isabs(path) else Path(path).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError(f"path {path!r} is outside the repository")
        if any(part.startswith(HIDDEN_PREFIX) for part in p.parts):
            raise ValueError(f"path {path!r} is not accessible")
        return p

    def _env(self) -> dict:
        path = os.environ.get("PATH", "/usr/bin:/bin")
        if self.bin_dir:
            path = f"{self.bin_dir}:{path}"
        return {"PATH": path, "HOME": str(self.root), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                "GIT_CEILING_DIRECTORIES": str(self.root.parent),
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(self.root), "TERM": "dumb",
                "TMPDIR": str(self.root / ".tmp")}

    def iter_files(self):
        for p in sorted(self.root.rglob("*")):
            if p.is_dir():
                continue
            rel = p.relative_to(self.root)
            if any(part in IGNORED_DIRS or part.startswith(HIDDEN_PREFIX) or part == ".tmp"
                   for part in rel.parts):
                continue
            yield rel, p

    def snapshot(self) -> dict[str, str]:
        """path -> content for every text file (used to detect which files a turn changed)."""
        out = {}
        for rel, p in self.iter_files():
            try:
                out[str(rel)] = p.read_text()
            except UnicodeDecodeError:
                out[str(rel)] = f"<binary {p.stat().st_size} bytes>"
        return out

    def repo_dump(self, max_file_chars: int = 20000) -> str:
        parts = ["Files:"]
        files = list(self.iter_files())
        for rel, _ in files:
            parts.append(f"  {rel}")
        parts.append("")
        for rel, p in files:
            try:
                txt = p.read_text()
            except UnicodeDecodeError:
                continue
            if len(txt) > max_file_chars:
                txt = txt[:max_file_chars] + f"\n... [truncated, {len(txt)} chars total]\n"
            fence = "````" if "```" in txt else "```"
            lang = {"py": "python", "md": "markdown", "json": "json", "jsonl": "json"}.get(p.suffix[1:], "")
            parts.append(f"### {rel}\n{fence}{lang}\n{txt}\n{fence}\n")
        return "\n".join(parts)

    # ---- tools ---------------------------------------------------------------------------
    def list_files(self) -> str:
        return "\n".join(str(rel) for rel, _ in self.iter_files()) or "(empty)"

    def read_file(self, path: str) -> str:
        p = self._resolve(path)
        if not p.exists():
            return f"ERROR: {path} does not exist"
        if p.is_dir():
            return "ERROR: is a directory"
        try:
            txt = p.read_text()
        except UnicodeDecodeError:
            return "ERROR: binary file"
        if len(txt) > MAX_OUTPUT_CHARS:
            return txt[:MAX_OUTPUT_CHARS] + (f"\n... [truncated: file is {len(txt)} chars; read the rest with a shell command such as "
                                             f"`sed -n START,ENDp {path}`]")
        return txt

    def write_file(self, path: str, content: str) -> str:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists()
        p.write_text(content)
        return f"{'Overwrote' if existed else 'Created'} {path} ({len(content)} chars)"

    def run_command(self, command: str, timeout: int = 120) -> str:
        if BLOCKED_RE.search(command):
            return "ERROR: command blocked by sandbox policy (no network access, sudo or process-wide commands)"
        if ESCAPE_TOKEN_RE.search(command):
            return "ERROR: command blocked by sandbox policy (paths must stay inside the repository: no ~, $HOME or ../)"
        for path in SENSITIVE_PATH_RE.findall(command):
            if not path.startswith(str(self.root)):
                return f"ERROR: path {path} is outside the repository"
        (self.root / ".tmp").mkdir(exist_ok=True)
        try:
            r = subprocess.run(command, shell=True, cwd=self.root, env=self._env(), capture_output=True,
                               text=True, timeout=timeout, errors="replace")
        except subprocess.TimeoutExpired:
            return f"ERROR: command timed out after {timeout}s"
        out = r.stdout
        if r.stderr:
            out += ("\n" if out else "") + "[stderr]\n" + r.stderr
        out = out.strip() or "(no output)"
        if len(out) > MAX_OUTPUT_CHARS:
            half = MAX_OUTPUT_CHARS // 2
            out = out[:half] + f"\n... [{len(out) - MAX_OUTPUT_CHARS} chars omitted] ...\n" + out[-half:]
        return f"exit code {r.returncode}\n{out}"


TOOLS = [
    {"type": "function", "function": {
        "name": "list_files", "description": "List all files in the repository.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a file from the repository.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Path relative to the repository root."}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or completely overwrite a file in the repository with the given content.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Path relative to the repository root."},
            "content": {"type": "string", "description": "The full new content of the file."}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "run_command",
        "description": ("Run a shell command in the repository root (e.g. `python -m pytest -q tests`, "
                        "`python script.py`, `grep -rn foo .`). No network access. Times out after 120 s."),
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "The shell command to run."}},
            "required": ["command"]}}},
]


def dispatch(sb: Sandbox, name: str, arguments: str) -> str:
    try:
        args = json.loads(arguments or "{}")
        if not isinstance(args, dict):
            return "ERROR: arguments must be a JSON object"
    except json.JSONDecodeError as e:
        return f"ERROR: could not parse tool arguments as JSON: {e}"
    try:
        if name == "list_files":
            return sb.list_files()
        if name == "read_file":
            return sb.read_file(str(args.get("path", "")))
        if name == "write_file":
            if "content" not in args:
                return "ERROR: write_file needs 'content'"
            return sb.write_file(str(args.get("path", "")), str(args["content"]))
        if name == "run_command":
            return sb.run_command(str(args.get("command", "")))
        return f"ERROR: unknown tool {name}"
    except ValueError as e:
        return f"ERROR: {e}"
    except Exception as e:  # noqa: BLE001 - surface any tool failure to the model, never crash the loop
        return f"ERROR: {type(e).__name__}: {e}"
