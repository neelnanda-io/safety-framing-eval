"""Render a paired task under one framing.

A task is written ONCE as a template whose framing-dependent words are `{{TOKENS}}`; each framing is a
JSON dict of token -> text. Rendering the same template under `safety` and `capabilities` therefore
yields codebases that are identical apart from names, comments, docs and the task blurb - the design
of the OpenAI report's evaluation.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sfe.config import TASKS_DIR

TOKEN_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".jsonl", ".csv", ".cfg", ".toml", ".ini", ".yaml", ".yml", ""}


@dataclass
class Task:
    id: str
    path: Path
    meta: dict
    framings: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def rubric(self) -> list[dict]:
        return self.meta["rubric"]

    @property
    def public_test_cmd(self) -> str:
        return self.meta.get("public_test_cmd", "python -m pytest -q tests")


def list_tasks() -> list[str]:
    return sorted(p.name for p in TASKS_DIR.iterdir() if (p / "task.json").exists())


def load_task(task_id: str) -> Task:
    path = TASKS_DIR / task_id
    meta = json.loads((path / "task.json").read_text())
    framings = {}
    for f in sorted((path / "framings").glob("*.json")):
        framings[f.stem] = json.loads(f.read_text())
    t = Task(id=task_id, path=path, meta=meta, framings=framings)
    check_task(t)
    return t


class RenderError(Exception):
    pass


def render_text(text: str, mapping: dict[str, str], where: str = "") -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in mapping:
            raise RenderError(f"unknown token {{{{{key}}}}} in {where}")
        return mapping[key]
    out = TOKEN_RE.sub(sub, text)
    if "{{" in out and TOKEN_RE.search(out):
        raise RenderError(f"token left after rendering {where}")
    return out


def render_dir(src: Path, dst: Path, mapping: dict[str, str]) -> list[Path]:
    """Render every file under src into dst (dst may already exist; files are overwritten)."""
    written = []
    for p in sorted(src.rglob("*")):
        if p.is_dir() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(src)
        rel_rendered = Path(render_text(str(rel), mapping, where=f"path {rel}"))
        out = dst / rel_rendered
        out.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix in TEXT_SUFFIXES:
            out.write_text(render_text(p.read_text(), mapping, where=str(rel)))
        else:
            shutil.copy2(p, out)
        written.append(out)
    return written


def mapping_for(task: Task, framing: str) -> dict[str, str]:
    if framing not in task.framings:
        raise RenderError(f"{task.id}: no framing {framing!r} (have {sorted(task.framings)})")
    return task.framings[framing]


def render_task(task: Task, framing: str, dest: Path) -> Path:
    """Render the agent-visible repository (template/) into dest. dest must not exist."""
    if dest.exists():
        raise RenderError(f"refusing to render into existing dir {dest}")
    dest.mkdir(parents=True)
    render_dir(task.path / "template", dest, mapping_for(task, framing))
    return dest


def render_hidden_tests(task: Task, framing: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    render_dir(task.path / "hidden_tests", dest, mapping_for(task, framing))
    return dest


def render_solution(task: Task, framing: str, dest: Path) -> Path:
    """Template plus the reference solution overlay - used only to validate the rubric is achievable."""
    render_task(task, framing, dest)
    render_dir(task.path / "solution", dest, mapping_for(task, framing))
    return dest


def tokens_in_dir(d: Path) -> set[str]:
    found = set()
    for p in d.rglob("*"):
        if p.is_file() and p.suffix in TEXT_SUFFIXES and "__pycache__" not in p.parts:
            found |= set(TOKEN_RE.findall(p.read_text()))
            found |= set(TOKEN_RE.findall(str(p.relative_to(d))))
    return found


def check_task(task: Task) -> None:
    """Structural checks: framings share one key set, every token used is defined, rubric ids unique."""
    keysets = {f: set(m) for f, m in task.framings.items()}
    for f in ("safety", "capabilities", "neutral"):
        if f not in keysets:
            raise RenderError(f"{task.id}: missing framing {f}")
    base = keysets["safety"]
    for f, ks in keysets.items():
        if ks != base:
            raise RenderError(f"{task.id}: framing {f} keys differ from safety: "
                              f"{sorted(ks ^ base)}")
    used = set()
    for sub in ("template", "hidden_tests", "solution"):
        if (task.path / sub).exists():
            used |= tokens_in_dir(task.path / sub)
    missing = used - base
    if missing:
        raise RenderError(f"{task.id}: tokens used but undefined: {sorted(missing)}")
    if "TASK_BLURB" not in base:
        raise RenderError(f"{task.id}: framings must define TASK_BLURB")
    ids = [r["id"] for r in task.rubric]
    if len(ids) != len(set(ids)):
        raise RenderError(f"{task.id}: duplicate rubric ids")


def neutralize(text: str, task: Task, framing: str) -> str:
    """Best-effort removal of framing words from free text (for the framing-blind judge):
    replace each framing value with the neutral framing's value, longest values first."""
    src = mapping_for(task, framing)
    neu = mapping_for(task, "neutral")
    pairs = sorted(((v, neu[k]) for k, v in src.items() if v and v != neu[k] and k != "TASK_BLURB"),
                   key=lambda kv: -len(kv[0]))
    out = text
    for a, b in pairs:
        # word boundaries where the value starts/ends with a word character, so "near" never hits "nearly"
        pat = (r"\b" if a[0].isalnum() or a[0] == "_" else "") + re.escape(a) + (r"\b" if a[-1].isalnum() or a[-1] == "_" else "")
        out = re.sub(pat, b, out, flags=re.IGNORECASE)
    return out
