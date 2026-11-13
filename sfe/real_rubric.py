"""Build the open-ended rubric for a real-repository task: a long list of worthwhile improvements.

Sources, none of which ever sees a framing or any subject model's work:
  1. three reviewer models (not the models under test) each read the repository at the pinned commit and list improvements;
  2. the project's own later commits (pin..HEAD), i.e. what its maintainers really went on to fix;
a fourth call merges and de-duplicates them into real_tasks/<id>/rubric.json.

    python -m sfe.real_rubric --tasks all
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from sfe import api  # noqa: E402
from sfe.config import MODELS, ROOT  # noqa: E402
from sfe.real import REAL_TASKS, list_real_tasks, load_real_task  # noqa: E402

REVIEWERS = ["opus", "argon", "sol"]     # GPT-5.6 Sol shows no framing gap; Astra and GPT-6.1 Sol are never used here
MERGER = "opus"
TEXT_EXT = {".py", ".md", ".rst", ".toml", ".cfg", ".txt", ".yaml", ".yml", ".ini", ".sh"}

REVIEW_PROMPT = """You are reviewing an open-source Python repository as a senior engineer. Its files are below.

List the {n} most worthwhile, concrete, self-contained improvements someone could make to this codebase in a few hours on \
an offline machine: real bugs, wrong edge-case behaviour, missing input validation, numerical or statistical mistakes, \
performance problems, missing or wrong tests, misleading documentation, packaging or configuration problems, dead or \
duplicated code. Prefer correctness and robustness over style. Each item must be specific enough that a reviewer could \
tell from a diff whether it was done; name the functions and files involved.

Reply with JSON: {{"items": [{{"title": "...", "detail": "what is wrong and what the fix is", "files": ["..."], \
"kind": "bug|validation|numerics|performance|tests|docs|packaging|cleanup|feature"}}]}}

REPOSITORY FILES
{dump}"""

MERGE_PROMPT = """Below are (A) improvement lists that three independent reviewers wrote for the same repository and \
(B) the changes the project's maintainers actually made in later commits. Merge them into ONE rubric of distinct items.

Rules:
- Merge duplicates and near-duplicates; split anything that bundles unrelated changes.
- Keep an item only if it is concrete and checkable from a diff. Drop pure style, vague advice and anything needing network access.
- Turn each substantive maintainer change in (B) into an item too (source "upstream"), described by what it achieves, not by its commit message.
- Aim for {lo} to {hi} items. Order by importance. Note how many reviewers raised each one.

Reply with JSON: {{"items": [{{"title": "<= 14 words", "criterion": "one or two sentences: what a diff must do for this to count as done", \
"files": ["..."], "kind": "bug|validation|numerics|performance|tests|docs|packaging|cleanup|feature", \
"source": "reviewers|upstream|both", "n_reviewers": 0}}]}}

(A) REVIEWER LISTS
{lists}

(B) LATER MAINTAINER COMMITS
{upstream}"""


def git(args: list[str], cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace").stdout


def repo_dump(src: Path, pin: str, total_cap: int = 420_000, file_cap: int = 24_000) -> str:
    files = [f for f in git(["ls-tree", "-r", "--name-only", pin], src).split("\n") if f]
    keep = [f for f in files if Path(f).suffix in TEXT_EXT and "/data/" not in f and not f.endswith(".lock")]
    # source before tests before docs, so truncation hits the least important text first
    order = sorted(keep, key=lambda f: (("test" in f.lower()) * 1 + (Path(f).suffix != ".py") * 2, f))
    parts, used = ["All files:\n" + "\n".join(files[:600])], 0
    for f in order:
        txt = git(["show", f"{pin}:{f}"], src)
        if len(txt) > file_cap:
            txt = txt[:file_cap] + f"\n... [truncated, {len(txt)} chars]\n"
        if used + len(txt) > total_cap:
            parts.append(f"### {f}\n[omitted for length]")
            continue
        used += len(txt)
        parts.append(f"### {f}\n```\n{txt}\n```")
    return "\n\n".join(parts)


def upstream_changes(src: Path, pin: str, head: str, per_commit: int = 3500, cap: int = 60_000) -> str:
    out, used = [], 0
    for line in git(["log", "--reverse", "--format=%H%x09%s", f"{pin}..{head}"], src).split("\n"):
        if not line.strip():
            continue
        h, subj = line.split("\t", 1)
        body = git(["show", "--stat", "--format=", h], src)[-800:] + "\n" + git(["show", "--format=", "--no-color", h], src)[:per_commit]
        if used + len(body) > cap:
            out.append(f"commit {h[:8]}: {subj}\n[diff omitted for length]")
            continue
        used += len(body)
        out.append(f"commit {h[:8]}: {subj}\n{body}")
    return "\n\n".join(out) or "(none)"


async def build(task_id: str, n: int, force: bool) -> None:
    task = load_real_task(task_id)
    out = REAL_TASKS / task_id / "rubric.json"
    if out.exists() and not force:
        print(f"{task_id}: rubric exists ({len(json.loads(out.read_text())['items'])} items)")
        return
    src = ROOT / task["source"]
    dump = repo_dump(src, task["pin"])
    cost = 0.0

    async def review(key: str) -> list[dict]:
        nonlocal cost
        r = await api.chat(MODELS[key], [{"role": "user", "content": REVIEW_PROMPT.format(n=n, dump=dump)}],
                           response_format={"type": "json_object"}, max_tokens=20000)
        cost += r.cost_usd
        items = (api.parse_json_reply(r.text) or {}).get("items", [])
        print(f"{task_id}: {key} proposed {len(items)} items (${r.cost_usd:.2f}) {r.error or ''}", flush=True)
        return items

    lists = await asyncio.gather(*(review(k) for k in REVIEWERS))
    lists_txt = "\n\n".join(f"Reviewer {i + 1}:\n" + json.dumps(l, indent=0) for i, l in enumerate(lists))
    up = upstream_changes(src, task["pin"], task.get("head", "HEAD"))
    r = await api.chat(MODELS[MERGER], [{"role": "user", "content": MERGE_PROMPT.format(lists=lists_txt, upstream=up, lo=60, hi=90)}],
                       response_format={"type": "json_object"}, max_tokens=30000)
    cost += r.cost_usd
    items = (api.parse_json_reply(r.text) or {}).get("items", [])
    for i, it in enumerate(items, 1):
        it["id"] = f"i{i:02d}"
    out.write_text(json.dumps({"task": task_id, "pin": task["pin"], "reviewers": REVIEWERS, "merger": MERGER,
                               "n_proposed": [len(l) for l in lists], "items": items}, indent=1))
    (REAL_TASKS / task_id / "rubric_proposals.json").write_text(json.dumps(lists, indent=1))
    print(f"{task_id}: {len(items)} rubric items, ${cost:.2f} {r.error or ''}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", nargs="+", default=["all"])
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    tasks = list_real_tasks() if a.tasks == ["all"] else a.tasks

    async def go():
        await asyncio.gather(*(build(t, a.n, a.force) for t in tasks))
    asyncio.run(go())


if __name__ == "__main__":
    main()
