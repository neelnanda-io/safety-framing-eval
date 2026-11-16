"""Build the public data release: every episode transcript, grouped into one archive per experiment, with local paths,
the local username and e-mail addresses scrubbed, and third-party repository contents withheld where the repository has
no licence.

    python scripts/pack_data.py plan                       # what would go where, with counts; writes nothing
    python scripts/pack_data.py pack --base dist/data-v2   # data-v3: data-v2's archives copied byte for byte, plus
                                                           # v3-additions.tar.gz with every file they do not hold
    python scripts/pack_data.py pack --out <dir>           # every archive packed afresh (how data-v2 was built)
    python scripts/pack_data.py pack --only new-repos      # one archive
    python scripts/pack_data.py pack --drop-encrypted --out <dir>   # same, encrypted reasoning blobs replaced (size test)
    python scripts/pack_data.py licences [--github]        # check the licence table against the clones (and GitHub)

Each archive unpacks at the repository root: `runs/<run>/{episodes,replaced,superseded}/*.json` and, for the first-reply
probes, `results/real/<folder>/*.json`, plus `THIRD_PARTY_NOTICES.md` and `LICENSES/<repository>.txt` when it holds
episodes on third-party repositories.

`data-v3` (16 Nov 2026) keeps the four archives of `data-v2` unchanged and adds `v3-additions.tar.gz`, packed by the same
rules from every file `data-v2` does not hold. Because each archive unpacks its own `THIRD_PARTY_NOTICES.md` at the root,
the added archive (which sorts last) carries the notice for the whole release and the licence text of every licensed
repository in it; the `LICENSES/` files inside the `data-v2` archives are placeholders, because the clones were not on
the machine that packed them.

What is changed on the way out (every JSON string, including dictionary keys, is processed after parsing):
  - absolute paths into the original machine's home folder become `<repo>`, `<venv>` or `<home>`;
  - the local username and the machine's host name (read at run time, never written here) become `<user>` and `<host>`,
    including fragments of the username left where long command output was cut in the middle of a path;
  - e-mail addresses become `<email>` (maintainers' addresses in `git log` output included), except the harness's
    fake identity and reserved example domains;
  - tool results in which an early toy-task agent saw this project's own git history are withheld;
  - episodes on a repository with NO licence keep the agent's own messages and reasoning summaries, every tool call's
    name and arguments (except the text of `write_file`, which is mostly the repository's own code), the test counts and
    per-file diff statistics, but the text of tool results, test output and diffs is replaced by a placeholder.
Episodes on the project's own toy tasks (`tasks/`) and on permissively licensed repositories are published in full.
"""
from __future__ import annotations

import argparse
import collections
import getpass
import hashlib
import io
import json
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
DEFAULT_OUT = ROOT / "dist" / "data-v3"
RELEASE = "data-v3"
# With `pack --base <earlier release>`: the earlier archives are copied unchanged and every file they do not hold goes into
# this one archive (16 Nov 2026: nine harmless-use episodes of two Claude models, eleven new descriptions).
ADDED = {"name": "v3-additions",
         "what": "files added after data-v2: the harmless use on Claude Fable 5.2 (seeds 1-5) and Claude Opus 5.5 (seeds 2-5) "
                 "on the generic RL library, and eleven new descriptions on GPT-6 Astra and GPT-6.1 Sol (the RL library and "
                 "the data kit): full episodes and first replies (16 Nov 2026)"}

# --------------------------------------------------------------------------------------------------------------------
# What goes into which archive. A run folder is packed when its name matches one pattern; folders that match none are
# listed in the manifest as "not packed" (abandoned attempts and one-off smoke tests), so a new run never vanishes
# silently. Sub-folders packed per run: the episodes, and the spoiled or superseded originals kept beside them.
ARCHIVES = {
    "toy-tasks": {
        "what": "the ten toy tasks (six original, four harder), every model, the description family and the replays "
                "with reasoning carried (5-10 Nov 2026)",
        "runs": [r"^main[23]_", r"^v1_main_", r"^w[234]_", r"^hard_(std|scarce)_", r"^native_", r"^pilot2?_astra$",
                 r"^calib_", r"^smoke7b?$", r"^fam_"],
        "dirs": [],
    },
    "real-repos": {
        "what": "six real open-source repositories under a safety and a product description, twenty-two models "
                "(10-13 Nov 2026)",
        "runs": [r"^real_", r"^real2_"],
        "dirs": [],
    },
    "description-edits": {
        "what": "single-change rewrites of the two attack-like descriptions, and the implied-purpose descriptions on "
                "twenty-two models: full episodes and first replies (11-13 Nov 2026)",
        "runs": [r"^real3_", r"^real4_", r"^real5_"],        # real5_: the five data-kit descriptions of 16 Nov
        "dirs": ["results/real/first_words"],
    },
    "new-repos": {
        "what": "eighteen further repositories, ControlArena on twenty-two models, and one generic library under stated "
                "uses: full episodes and first replies (13 Nov 2026)",
        "runs": [r"^new_"],
        "dirs": ["results/real/new_repos_first_words*", "results/real/new_wordings_first_words"],   # the latter: 16 Nov
    },
}
RUN_SUBDIRS = ("episodes", "replaced", "superseded")

# --------------------------------------------------------------------------------------------------------------------
# Licence of every third-party repository an agent worked in, at the pinned commit in real_tasks*/<id>/task.json.
# Checked 13 Nov 2026 against the licence file at the pin in the local clone and against GitHub's licence API
# (`python scripts/pack_data.py licences --github`). None = no licence file and no licence on GitHub: all rights reserved,
# so the repository's contents are withheld from the transcripts (rule "withheld"). Edit this table to overrule.
LICENCES = {
    # the six repositories of the original real-repository study (real_tasks/)
    "rsl_rl": "BSD-3-Clause",
    "valor": "MIT",
    "prompto": "MIT",
    "synthetic-data-kit": "MIT",
    "NeuroX": "BSD-3-Clause",
    "dictionary_learning": "MIT",
    # the eighteen of the new-repository test (real_tasks_new/)
    "alignment_faking": "MIT",
    "amlsim": "Apache-2.0",
    "auditbench": None,
    "captcha": "BSD-3-Clause",
    "causal": "MIT",
    "control_arena": "MIT",
    "em_organisms": None,
    "fingerprint": "MIT",
    "honeypot": "BSD-3-Clause",
    "new_datagen": "Apache-2.0",
    "new_rl": "MIT",
    "oml_fingerprint": "Apache-2.0",
    "pw_locked": None,
    "sandbag_games": "MIT",
    "sandbag_organism": None,
    "sleeper_agents": None,
    "subliminal": "MIT",
    "watermark": "Apache-2.0",
}
LICENCE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING")

# --------------------------------------------------------------------------------------------------------------------
# Scrubbing. The username is read at run time so that it is never written into this (published) file.
USER = getpass.getuser()
ABS = re.compile(r"/(?:Users|home)/[^/\s\"'<>]+/Code/safety-framing-eval")
VENV = re.compile(r"/(?:Users|home)/[^/\s\"'<>]+/\.venvs/[^/\s\"'<>]+")
MAC_HOME = re.compile(r"/(?:Users)/[A-Za-z0-9._-]*")                 # any macOS home folder, including truncated ones
LINUX_HOME = re.compile(rf"/home/{re.escape(USER)}\b") if USER else None
# The machine's host name, e.g. inside TensorBoard log file names (events.out.tfevents.<time>.<host>.<pid>.<n>).
_HOSTS = sorted({h for h in (socket.gethostname(), socket.gethostname().split(".")[0]) if len(h) >= 4}, key=len, reverse=True)
HOST_RE = re.compile("|".join(re.escape(h) for h in _HOSTS), re.I) if _HOSTS else None
USER_WORD = re.compile(rf"(?<![A-Za-z0-9]){re.escape(USER)}(?![A-Za-z0-9])", re.I) if len(USER) >= 4 else None
# Fragments of the username where the harness cut long command output in the middle of a path ("... [1609 chars
# omitted] ...<end of the username>/Code/..."): a proper suffix right before "/Code/" (tail of a cut), or a proper
# prefix right after "/home/" (head of a cut; the macOS home-folder form is already caught by MAC_HOME). Built from the
# run-time username.
_TAILS = [USER[i:] for i in range(1, len(USER))] if len(USER) >= 4 else []          # longest first
_HEADS = [USER[:i] for i in range(len(USER) - 1, 0, -1)] if len(USER) >= 4 else []  # longest first
USER_TAIL = re.compile(rf"(?<![A-Za-z0-9])(?:{'|'.join(map(re.escape, _TAILS))})(?=/Code/)") if _TAILS else None
USER_HEAD = re.compile(rf"/home/(?:{'|'.join(map(re.escape, _HEADS))})(?![A-Za-z0-9])") if _HEADS else None
# An address needs a real top-level domain and must not run on into a name, so code such as `q@k.transpose(...)`,
# `x@torch.no_grad` or `@pytest.mark.parametrize` is left alone.
TLDS = (r"com|org|net|edu|gov|mil|int|io|ai|dev|app|co|me|info|biz|us|uk|eu|de|fr|ch|nl|be|at|se|dk|fi|it|es|pt|ie|pl|cz|"
        r"il|in|cn|jp|kr|tw|hk|sg|au|nz|ca|br|mx|ru|qa|ae|za")
EMAIL = re.compile(rf"(?<![\w.%+-])[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+(?:{TLDS})(?![\w(-])", re.I)
# Kept: the harness's fake git identity, the Claude co-author line, ssh git remotes, reserved example domains (RFC 2606).
EMAIL_KEEP = re.compile(r"^(?:akim@users\.noreply\.github\.com|noreply@anthropic\.com|git@(?:github\.com|gitlab\.com|bitbucket\.org))$|"
                        r"@(?:[A-Za-z0-9-]+\.)*(?:example\.(?:com|org|net)|example|invalid|test|localhost)$", re.I)


HOME_TILDE = re.compile(r"~/(?:Code)\b")                           # the original machine's code folder


def scrub(s: str) -> str:
    if "~/" in s:
        s = HOME_TILDE.sub("<home>/Code", s)
    if "/" in s:
        s = ABS.sub("<repo>", s)
        s = VENV.sub("<venv>", s)
        s = MAC_HOME.sub("<home>", s)
        if LINUX_HOME:
            s = LINUX_HOME.sub("<home>", s)
        if USER_HEAD:
            s = USER_HEAD.sub("<home>", s)
        if USER_TAIL and "/Code/" in s:
            s = USER_TAIL.sub("<user>", s)
    if HOST_RE and HOST_RE.search(s):
        s = HOST_RE.sub("<host>", s)
    if USER_WORD and USER_WORD.search(s):
        s = USER_WORD.sub("<user>", s)
    if "@" in s:
        s = EMAIL.sub(lambda m: m.group(0) if EMAIL_KEEP.search(m.group(0)) else "<email>", s)
    return s


def scrub_tree(x):
    if isinstance(x, str):
        return scrub(x)
    if isinstance(x, list):
        return [scrub_tree(v) for v in x]
    if isinstance(x, dict):
        opaque = OPAQUE_KEYS if is_encrypted(x) or x.get("type") == "reasoning.text" else ()
        return {scrub(k): (v if k in opaque else scrub_tree(v)) for k, v in x.items()}
    return x


# --------------------------------------------------------------------------------------------------------------------
# Encrypted reasoning: opaque provider blobs that cannot be read without the provider's key. They are never scrubbed
# (changing a character would only corrupt them) and are measured separately.
OPAQUE_KEYS = ("data", "encrypted_content", "signature")


def is_encrypted(d: dict) -> bool:
    return d.get("type") == "reasoning.encrypted" or "encrypted_content" in d


def encrypted_bytes(x) -> int:
    n = 0
    if isinstance(x, dict):
        if d_is := is_encrypted(x):
            n += len(str(x.get("data") or x.get("encrypted_content") or ""))
        if x.get("type") == "reasoning.text" and isinstance(x.get("signature"), str):
            n += len(x["signature"])
        n += sum(encrypted_bytes(v) for k, v in x.items() if not (d_is and k in ("data", "encrypted_content")))
    elif isinstance(x, list):
        n += sum(encrypted_bytes(v) for v in x)
    return n


def drop_encrypted(x):
    if isinstance(x, dict):
        y = {k: drop_encrypted(v) for k, v in x.items()}
        if is_encrypted(x):
            for k in ("data", "encrypted_content"):
                if isinstance(x.get(k), str):
                    y[k] = f"[encrypted reasoning removed: {len(x[k])} characters]"
        if x.get("type") == "reasoning.text" and isinstance(x.get("signature"), str):
            y["signature"] = f"[signature removed: {len(x['signature'])} characters]"
        return y
    if isinstance(x, list):
        return [drop_encrypted(v) for v in x]
    return x


# --------------------------------------------------------------------------------------------------------------------
# Repositories and the licence rule.
def task_table() -> dict:
    """task id -> {"url", "pin", "licence", "rule", "source"} for every real-repository task, from the task files."""
    out = {}
    for d in ("real_tasks", "real_tasks_new"):
        for f in sorted((ROOT / d).glob("*/task.json")):
            t = json.loads(f.read_text())
            tid = f.parent.name
            if tid in out:
                raise SystemExit(f"task id {tid} appears in two task folders")
            if tid not in LICENCES:
                raise SystemExit(f"{d}/{tid} is not in the LICENCES table of scripts/pack_data.py: check its licence and add it")
            url = t["url"].removesuffix(".git")
            lic = LICENCES[tid]
            out[tid] = {"url": url, "pin": t["pin"], "licence": lic or "none", "rule": "full" if lic else "withheld",
                        "source": t.get("source"), "folder": d}
    return out


TOY_TASKS = {p.name for p in (ROOT / "tasks").iterdir() if p.is_dir()}


def placeholder(what: str, task: str, n: int) -> str:
    return (f"[withheld: {what} ({n} characters) from the repository behind task `{task}`, which has no licence, "
            f"so its contents are not redistributed; see THIRD_PARTY_NOTICES.md]")


def diff_stats(diff: str) -> dict:
    """Lines added and removed per file of a `git diff` (counted inside hunks only)."""
    files, cur, in_hunk = {}, None, False
    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*?) b/(.*)$", line)
            cur, in_hunk = (m.group(2) if m else line[11:]), False
            files.setdefault(cur, [0, 0])
        elif line.startswith("@@") and cur is not None:
            in_hunk = True
        elif not in_hunk:
            continue
        elif line.startswith("+"):
            files[cur][0] += 1
        elif line.startswith("-"):
            files[cur][1] += 1
    return {"files": {k: {"added": a, "removed": r} for k, (a, r) in files.items()},
            "added": sum(a for a, _ in files.values()), "removed": sum(r for _, r in files.values())}


def _withhold_args(name: str, args, task: str):
    """Tool-call arguments with the text of a written file replaced (path and size kept)."""
    if name != "write_file":
        return args
    as_text = isinstance(args, str)
    try:
        a = json.loads(args) if as_text else dict(args)
    except (json.JSONDecodeError, TypeError, ValueError):
        return placeholder("write_file arguments", task, len(str(args)))
    if isinstance(a, dict) and isinstance(a.get("content"), str):
        c = a["content"]
        a["content"] = placeholder(f"file text, {c.count(chr(10)) + 1} lines", task, len(c))
    return json.dumps(a, ensure_ascii=False) if as_text else a


def withhold(d: dict, task: str) -> dict:
    """Apply the no-licence rule to an episode or first-reply record, in place. Returns d."""
    for m in d.get("messages") or []:
        if m.get("role") == "tool" and isinstance(m.get("content"), str):
            m["content"] = placeholder("tool result", task, len(m["content"]))
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") or {}
            if "arguments" in fn:
                fn["arguments"] = _withhold_args(fn.get("name"), fn["arguments"], task)
    for t in d.get("turns") or []:
        for c in t.get("calls") or []:
            if isinstance(c.get("result_head"), str):
                c["result_head"] = placeholder("tool result", task, len(c["result_head"]))
            if "args" in c:
                c["args"] = _withhold_args(c.get("name"), c["args"], task)
        if isinstance(t.get("diff"), str):
            t["diff_stats"] = diff_stats(t["diff"])
            t["diff"] = placeholder("diff", task, len(t["diff"])) if t["diff"] else ""
    if isinstance(d.get("final_diff"), str):
        d["final_diff_stats"] = diff_stats(d["final_diff"])
        d["final_diff"] = placeholder("diff", task, len(d["final_diff"])) if d["final_diff"] else ""
    for k in ("tests_before", "tests_after"):
        if isinstance(d.get(k), dict) and isinstance(d[k].get("tail"), str):
            d[k]["tail"] = placeholder("test output", task, len(d[k]["tail"]))
    for k in ("calls_before", "next_calls"):
        for c in d.get(k) or []:
            if "arguments" in c:
                c["arguments"] = _withhold_args(c.get("name"), c["arguments"], task)
            if isinstance(c.get("result"), str):
                c["result"] = placeholder("tool result", task, len(c["result"]))
    d["withheld"] = {"why": "the repository has no licence", "kept": "the agent's messages and reasoning summaries, "
                     "tool names and arguments (written file text excepted), test counts, diff statistics",
                     "replaced": "tool results, written file text, test output, diffs"}
    return d


# --------------------------------------------------------------------------------------------------------------------
# Until 6 Nov 2026 toy-task sandboxes sat inside this project's own git repository, so an agent that ran `git log -p`
# saw the project's history, including its private development log (docs/NOTES.md, "Episode paths leaked"). Those tool
# results are withheld by default; `--keep-own-history` keeps them.
OWN_HISTORY = re.compile(r"project_memory\.md|# Project Memory")


def withhold_own_history(d: dict) -> int:
    n = 0
    note = ("[withheld: this output showed the git history of the harness's own repository, which leaked into the "
            "sandbox (see docs/NOTES.md, 'Episode paths leaked'), including a private development log]")
    for m in d.get("messages") or []:
        if m.get("role") == "tool" and isinstance(m.get("content"), str) and OWN_HISTORY.search(m["content"]):
            m["content"], n = note, n + 1
    for t in d.get("turns") or []:
        for c in t.get("calls") or []:
            if isinstance(c.get("result_head"), str) and OWN_HISTORY.search(c["result_head"]):
                c["result_head"], n = note, n + 1
    if n:
        d["withheld_own_history"] = n
    return n


# --------------------------------------------------------------------------------------------------------------------
# Selecting files.
def archive_of_run(run: str) -> str | None:
    for name, spec in ARCHIVES.items():
        if any(re.search(p, run) for p in spec["runs"]):
            return name
    return None


def plan(skip_runs: list | None = None) -> tuple[dict, list]:
    """archive -> list of (source path, archive member name, unit) ; plus the run folders not packed.
    `skip_runs`: patterns for runs still in progress, left out of this packing and listed as such."""
    out = {name: [] for name in ARCHIVES}
    skipped = []
    for run_dir in sorted(p for p in RUNS.iterdir() if p.is_dir()):
        run = run_dir.name
        a = archive_of_run(run)
        files = [f for sub in RUN_SUBDIRS for f in sorted((run_dir / sub).glob("*.json"))]
        if a is not None and any(re.search(p, run) for p in skip_runs or []):
            skipped.append({"run": run, "files": len(files), "why": "still running: packed at the last pass"})
            continue
        if a is None:
            skipped.append({"run": run, "files": len(files), "why": "abandoned attempt or one-off smoke test"})
            continue
        out[a] += [(f, f"runs/{run}/{f.parent.name}/{f.name}", f"runs/{run}") for f in files]
    for name, spec in ARCHIVES.items():
        for pattern in spec["dirs"]:
            for d in sorted(p for p in ROOT.glob(pattern) if p.is_dir()):
                rel = d.relative_to(ROOT).as_posix()
                out[name] += [(f, f"{rel}/{f.name}", rel) for f in sorted(d.glob("*.json"))]
    return out, skipped


def _task_of(d: dict) -> str | None:
    if isinstance(d.get("spec"), dict):
        return d["spec"].get("task")
    return d.get("task")


def transform(job) -> tuple:
    """One file: (member name, bytes, info dict). Runs in a worker process."""
    src, member, unit, tasks, drop_enc, keep_history = job
    raw = Path(src).read_bytes()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as e:      # e.g. an episode still being written by a running job
        return member, None, {"unit": unit, "error": f"unreadable JSON: {e}"}
    task = _task_of(d)
    if task in tasks:
        rule = tasks[task]["rule"]
    elif task in TOY_TASKS:
        rule = "own"
    else:
        raise RuntimeError(f"{member}: task {task!r} is neither a toy task nor in real_tasks*/: cannot decide its licence")
    enc = encrypted_bytes(d)
    d = scrub_tree(d)
    if rule == "withheld":
        withhold(d, task)
    own_history = 0 if keep_history or rule != "own" else withhold_own_history(d)
    if drop_enc:
        d = drop_encrypted(d)
    incomplete = member.startswith("runs/") and d.get("complete") is False
    b = json.dumps(d, indent=1).encode()
    return member, b, {"unit": unit, "task": task, "rule": rule, "raw_bytes": len(raw), "bytes": len(b),
                       "incomplete": incomplete, "own_history": own_history,
                       "encrypted_bytes": enc, "kind": member.split("/")[2] if member.startswith("runs/") else "first_reply"}


def notices(tasks: dict, used: set) -> tuple[str, dict]:
    """THIRD_PARTY_NOTICES.md text and {LICENSES/<task>.txt: text} for the repositories in `used`."""
    lines = ["# Third-party repositories in these transcripts", "",
             "The agents in these episodes worked in checkouts of the open-source repositories below, so tool results, "
             "diffs and written files contain their code. Each repository's licence applies to that content; the "
             "licence text at the pinned commit is in `LICENSES/`. Repositories with no licence are all rights "
             "reserved: for those, the text of tool results, test output, diffs and written files is replaced by a "
             "placeholder, and the agent's own messages, tool names and arguments and diff statistics are kept.", "",
             "| task | repository | pinned commit | licence | in these transcripts |", "|---|---|---|---|---|"]
    texts = {}
    for tid in sorted(used, key=str.lower):
        t = tasks[tid]
        rule = "in full" if t["rule"] == "full" else "contents withheld"
        lines.append(f"| `{tid}` | {t['url']} | `{t['pin'][:12]}` | {t['licence']} | {rule} |")
        if t["rule"] == "full":
            txt = licence_text(t)
            texts[f"LICENSES/{tid}.txt"] = (f"Licence of {t['url']} at commit {t['pin']}\n\n" +
                                            (txt or f"(licence file not available locally; see {t['url']})\n"))
    lines += ["", "The project's own code and the toy tasks under `tasks/` are MIT-licensed (see the repository)."]
    return "\n".join(lines) + "\n", texts


def licence_text(t: dict) -> str | None:
    """The licence file at the pinned commit, read from the local clone (None when the clone is not available)."""
    src = ROOT / (t.get("source") or "")
    if not (t.get("source") and (src / ".git").exists()):
        return None
    for name in LICENCE_FILES:
        r = subprocess.run(["git", "-C", str(src), "show", f"{t['pin']}:{name}"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
    return None


def add_bytes(tar: tarfile.TarFile, name: str, b: bytes, mtime: float):
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = len(b), int(mtime), 0o644
    tar.addfile(info, io.BytesIO(b))


def _new_unit(name: str) -> dict:
    return {"archive": name, "files": 0, "episodes": 0, "replaced": 0, "superseded": 0, "first_replies": 0, "incomplete": 0,
            "raw_bytes": 0, "bytes": 0, "encrypted_bytes": 0, "rules": collections.Counter(), "tasks": set()}


COUNTED = ("files", "episodes", "replaced", "superseded", "first_replies", "incomplete", "raw_bytes", "bytes", "encrypted_bytes")


def pack_archive(pool, path: Path, name: str, members: list, tasks: dict, drop_enc: bool, keep_history: bool,
                 manifest: dict, now: float, notice_also: set = frozenset()) -> tuple[dict, dict]:
    """Pack `members` [(source, member name, unit)] into `path`. Returns the archive's manifest entry and its units.
    `notice_also`: further repositories for the archive's THIRD_PARTY_NOTICES.md and LICENSES/ (the added archive of a
    release built on an earlier one names every repository of the release)."""
    used, n, digests = set(), 0, {}
    units = collections.OrderedDict()
    with tarfile.open(path, "w:gz", compresslevel=9) as tar:
        jobs = [(str(src), member, unit, tasks, drop_enc, keep_history) for src, member, unit in members]
        for member, b, info in pool.imap(transform, jobs, chunksize=4):
            if b is None:
                manifest.setdefault("unreadable", []).append({"file": member, "error": info["error"]})
                print(f"  SKIPPED {member}: {info['error']}")
                continue
            add_bytes(tar, member, b, now)
            digests[member] = hashlib.sha256(b).hexdigest()
            n += 1
            if info["rule"] in ("full", "withheld"):
                used.add(info["task"])
            u = units.setdefault(info["unit"], _new_unit(name))
            u["files"] += 1
            u["first_replies" if info["kind"] == "first_reply" else info["kind"]] += 1
            u["incomplete"] += info["incomplete"]
            if info["own_history"]:
                manifest.setdefault("own_history_withheld", {})[member] = info["own_history"]
            for k in ("raw_bytes", "bytes", "encrypted_bytes"):
                u[k] += info[k]
            u["rules"][info["rule"]] += 1
            u["tasks"].add(info["task"])
        if used | set(notice_also):
            text, lic = notices(tasks, used | set(notice_also))
            add_bytes(tar, "THIRD_PARTY_NOTICES.md", text.encode(), now)
            for k, v in lic.items():
                add_bytes(tar, k, v.encode(), now)
                digests[k] = hashlib.sha256(v.encode()).hexdigest()
            digests["THIRD_PARTY_NOTICES.md"] = hashlib.sha256(text.encode()).hexdigest()
    bad = verify(path, digests)          # read the archive back: every member must match what was written
    if bad:
        raise SystemExit(f"{path.name}: {len(bad)} member(s) differ from what was written, e.g. {bad[:3]}. "
                         "Nothing is wrong with the source files; pack again (and check free memory).")
    for u in units.values():
        u["rules"] = dict(u["rules"])
        u["tasks"] = sorted(u["tasks"], key=str.lower)
    size = path.stat().st_size
    entry = {"file": path.name, "what": "", "files": n, "bytes": size, "sha256": sha256(path), "units": list(units),
             "third_party": sorted(used, key=str.lower), "members_sha256": digests}
    print(f"{name}: {n} files, {size / 1e6:.0f} MB")
    return entry, units


def pack(out: Path, only: list | None, drop_enc: bool, workers: int, keep_history: bool = False,
         skip_runs: list | None = None) -> dict:
    tasks = task_table()
    files, skipped = plan(skip_runs)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"release": RELEASE, "built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                "encrypted_reasoning": "removed" if drop_enc else "kept", "archives": {}, "units": {},
                "not_packed": skipped, "repositories": tasks}
    for t in manifest["repositories"].values():
        t.pop("source", None)
    now = time.time()
    with Pool(workers) as pool:
        for name, members in files.items():
            if only and name not in only:
                continue
            entry, units = pack_archive(pool, out / f"{name}.tar.gz", name, members, tasks, drop_enc, keep_history,
                                        manifest, now)
            entry["what"] = ARCHIVES[name]["what"]
            manifest["units"].update(units)
            manifest["archives"][name] = entry
    if not only:
        write_release_files(out, manifest, tasks)
    return manifest


def write_release_files(out: Path, manifest: dict, tasks: dict):
    text, _ = notices(tasks, {t for a in manifest["archives"].values() for t in a["third_party"]})
    (out / "THIRD_PARTY_NOTICES.md").write_text(text)
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1))
    (out / "MANIFEST.md").write_text(manifest_md(manifest))
    (out / "RELEASE_NOTES.md").write_text(release_notes(manifest))


def archive_counts(units: dict, names: list) -> dict:
    k = collections.Counter()
    for u in names:
        for x in ("episodes", "replaced", "superseded", "first_replies"):
            k[x] += units[u][x]
    return dict(k)


def copy_file(src: Path, dst: Path):
    """A byte-for-byte copy; on macOS a copy-on-write clone (`cp -c`), which takes no extra disk space."""
    if sys.platform == "darwin" and subprocess.run(["cp", "-c", str(src), str(dst)]).returncode == 0:
        return
    shutil.copyfile(src, dst)


def pack_onto(base: Path, out: Path, workers: int) -> dict:
    """A release built on an earlier one: the earlier release's archives copied byte for byte (their SHA-256 checked
    against its manifest), and every file the plan packs that they do not hold, packed by the same rules into ADDED."""
    bm = json.loads((base / "MANIFEST.json").read_text())
    if bm.get("encrypted_reasoning") != "kept":
        raise SystemExit("the base release dropped encrypted reasoning; pack the additions the same way first")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty: write a release into a new folder")
    tasks = task_table()
    files, skipped = plan()
    have = {m for a in bm["archives"].values() for m in a["members_sha256"]}
    members = [(src, member, unit) for mem in files.values() for src, member, unit in mem if member not in have]
    out.mkdir(parents=True, exist_ok=True)
    for a in bm["archives"].values():
        copy_file(base / a["file"], out / a["file"])
        if sha256(out / a["file"]) != a["sha256"]:
            raise SystemExit(f"{a['file']}: the copy differs from the base release's manifest")
        print(f"{a['file']}: copied from {bm['release']} (SHA-256 checked)")
    repos = {t: dict(v) for t, v in tasks.items()}
    for v in repos.values():
        v.pop("source", None)
    manifest = {"release": RELEASE, "built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                "encrypted_reasoning": "kept",
                "base": {"release": bm["release"], "built": bm["built"], "archives": [a["file"] for a in bm["archives"].values()],
                         "how": "copied byte for byte; each archive's SHA-256 equals the base release's manifest"},
                "archives": {}, "units": {}, "not_packed": skipped, "repositories": repos}
    for name, a in bm["archives"].items():
        manifest["archives"][name] = dict(a, counts=archive_counts(bm["units"], a["units"]))
    manifest["units"] = {k: dict(v) for k, v in bm["units"].items()}
    for k in ("own_history_withheld", "unreadable"):
        if bm.get(k):
            manifest[k] = bm[k]
    release_repos = {t for a in bm["archives"].values() for t in a["third_party"]}
    with Pool(workers) as pool:
        entry, units = pack_archive(pool, out / f"{ADDED['name']}.tar.gz", ADDED["name"], members, tasks, False, False,
                                    manifest, time.time(), notice_also=release_repos)
    entry["what"] = ADDED["what"]
    entry["counts"] = archive_counts(units, list(units))
    manifest["archives"][ADDED["name"]] = entry
    for k, u in units.items():                     # a run folder can be partly in an earlier archive and partly added
        if k in manifest["units"]:
            old = manifest["units"][k]
            merged = {"archive": f"{old['archive']}, {ADDED['name']}", **{c: old.get(c, 0) + u[c] for c in COUNTED},
                      "rules": dict(collections.Counter(old["rules"]) + collections.Counter(u["rules"])),
                      "tasks": sorted(set(old["tasks"]) | set(u["tasks"]), key=str.lower),
                      "added": {c: u[c] for c in ("episodes", "replaced", "superseded", "first_replies")}}
            manifest["units"][k] = merged
        else:
            manifest["units"][k] = u
    write_release_files(out, manifest, tasks)
    return manifest


def verify(path: Path, digests: dict) -> list:
    """Members whose bytes, read back from the finished archive, do not match the checksum taken when they were added."""
    bad, seen = [], set()
    with tarfile.open(path, "r:gz") as tar:
        for m in tar:
            if m.isfile():
                seen.add(m.name)
                if hashlib.sha256(tar.extractfile(m).read()).hexdigest() != digests.get(m.name):
                    bad.append(m.name)
    return bad + sorted(set(digests) - seen)


def release_notes(m: dict) -> str:
    """The short text for the GitHub release page, with every number taken from the manifest."""
    per = {name: (a, collections.Counter(a.get("counts") or archive_counts(m["units"], a["units"])))
           for name, a in m["archives"].items()}
    what = {"toy-tasks": "the ten toy tasks, every model",
            "real-repos": "six real repositories, twenty-two models",
            "description-edits": "rewritten descriptions of the two attack-like repositories, and the purpose-implied ones",
            "new-repos": "further repositories, ten stated uses of one library, ControlArena",
            ADDED["name"]: "added after data-v2: the harmless use on two Claude models, eleven new descriptions on GPT-6 Astra "
                           "and GPT-6.1 Sol"}
    total = sum(a["files"] for a, _ in per.values())
    if m.get("base"):
        b = m["base"]
        added = per[ADDED["name"]][1]
        head = (f"Episode transcripts for every experiment in this repository ({total:,} files). Supersedes `{b['release']}`: its "
                f"{len(b['archives'])} archives are included unchanged (same SHA-256), and `{ADDED['name']}.tar.gz` adds "
                f"{added['episodes']:,} episodes and {added['first_replies']:,} first replies run since.")
    else:
        head = f"Episode transcripts for every experiment in this repository ({total:,} files). Supersedes `data-v1`, which held the toy tasks only."
    lines = [head, "", "| archive | contents | size |", "|---|---|---|"]
    for name, (a, k) in per.items():
        parts = [f"{k['episodes']:,} episodes"] + ([f"{k['first_replies']:,} first replies"] if k["first_replies"] else [])
        extra = ([f"{k['replaced']} spoiled original{'s' if k['replaced'] != 1 else ''}"] if k["replaced"] else []) + \
                ([f"{k['superseded']} superseded"] if k["superseded"] else [])
        lines.append(f"| `{a['file']}` | {what.get(name, a['what'])}: {' and '.join(parts)}"
                     f"{' (plus ' + ', '.join(extra) + ')' if extra else ''} | {a['bytes'] / 1e6:.1f} MB |")
    withheld = sorted(t for t, v in m["repositories"].items() if v["rule"] == "withheld")
    lines += ["", "Unpack at the repository root with `for f in *.tar.gz; do tar xzf \"$f\"; done` (creates `runs/<run>/...` and "
              "`results/real/<first-reply folders>/`); `docs/RUNS.md` says which run is which."]
    if m.get("base"):
        n_lic = sum(1 for v in m["repositories"].values() if v["rule"] == "full")
        lines += [f"Licence texts: the `LICENSES/` files inside the {len(m['base']['archives'])} `{m['base']['release']}` archives are "
                  "placeholders that only name each repository and link to it. `" + ADDED["name"] + ".tar.gz` carries the full "
                  f"licence text of all {n_lic} licensed repositories in `LICENSES/`, and `THIRD_PARTY_NOTICES.md` for the whole "
                  "release; it sorts last, so the loop above unpacks it last and leaves the full texts in place. If you unpack "
                  "only some archives, take `LICENSES/` from `" + ADDED["name"] + ".tar.gz`."]
    lines += ["Scrubbed on the way out: absolute local paths, the local username and host name, and e-mail addresses "
              "(`<repo>`, `<home>`, `<user>`, `<host>`, `<email>`).",
              f"{len(withheld)} repositories have no licence "
              f"({', '.join(m['repositories'][t]['url'].split('github.com/')[-1] for t in withheld)}): in their episodes the text "
              "of tool results, test output, diffs and written files is replaced by a placeholder. `THIRD_PARTY_NOTICES.md` "
              "lists every repository, its licence and pinned commit.",
              "`MANIFEST.md` and `MANIFEST.json` (attached) have per-run counts and the SHA-256 of every archive and every file."]
    return "\n".join(lines) + "\n"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_md(m: dict) -> str:
    lines = [f"# {m['release']} manifest", "", f"Built {m['built']}. Encrypted reasoning blobs: {m['encrypted_reasoning']}. "
             "`MANIFEST.json` holds the SHA-256 of every archive and of every file inside it; \"unfinished\" counts "
             "episodes whose `complete` field is false (cut off by a spend cap, a provider refusal or a lost connection).",
             "", "| archive | files | size | what |", "|---|---|---|---|"]
    for a in m["archives"].values():
        lines.append(f"| `{a['file']}` | {a['files']:,} | {a['bytes'] / 1e6:,.0f} MB | {a['what']} |")
    if m.get("base"):
        lines += ["", f"The first {len(m['base']['archives'])} archives are `{m['base']['release']}`'s (built {m['base']['built']}), "
                  f"copied byte for byte; `{ADDED['name']}.tar.gz` holds every file added since. A run folder split between "
                  "two archives is listed once below, with both archives and its total."]
    lines += ["", "Rule per file: `own` = the project's own toy task, in full; `full` = permissively licensed repository, "
              "in full; `withheld` = repository with no licence, contents replaced by a placeholder.", "",
              "| run or folder | archive | episodes | replaced | superseded | first replies | unfinished | MB (as packed) | rules | tasks |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for k, u in m["units"].items():
        rules = ", ".join(f"{r} {c}" for r, c in sorted(u["rules"].items()))
        tasks = ", ".join(u["tasks"]) if len(u["tasks"]) <= 6 else f"{len(u['tasks'])} tasks"
        lines.append(f"| `{k}` | {u['archive']} | {u['episodes']} | {u['replaced']} | {u['superseded']} | "
                     f"{u['first_replies']} | {u.get('incomplete', 0)} | {u['bytes'] / 1e6:.1f} | {rules} | {tasks} |")
    if m["not_packed"]:
        lines += ["", "Run folders on disk that are not packed: " +
                  ", ".join(f"`{s['run']}` ({s['files']} files; {s.get('why', 'not packed')})" for s in m["not_packed"]) + "."]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------------------------------
# Licence verification.
def detect_licence(text: str) -> str | None:
    t = " ".join(text.split())
    if "Apache License" in t and "Version 2.0" in t:
        return "Apache-2.0"
    if "Permission is hereby granted, free of charge" in t:
        return "MIT"
    if "Redistribution and use in source and binary forms" in t:
        return "BSD-3-Clause" if "Neither the name" in t or "names of its contributors" in t else "BSD-2-Clause"
    if "GNU GENERAL PUBLIC LICENSE" in t.upper():
        return "GPL"
    return "unrecognised"


def check_licences(github: bool) -> int:
    tasks, bad = task_table(), 0
    print(f"{'task':20} {'table':14} {'file at pin':14} {'GitHub':14} url")
    for tid, t in tasks.items():
        txt = licence_text(t)
        local = detect_licence(txt) if txt else ("none" if (ROOT / (t["source"] or "") / ".git").exists() else "no clone")
        gh = ""
        if github:
            slug = t["url"].split("github.com/")[1]
            r = subprocess.run(["gh", "api", f"repos/{slug}", "--jq", ".license.spdx_id // \"none\""],
                               capture_output=True, text=True)
            gh = r.stdout.strip() or f"error: {r.stderr.strip()[:40]}"
        want = t["licence"]
        ok = (local in (want, "no clone")) and (not github or gh in (want, "NOASSERTION"))
        bad += not ok
        print(f"{tid:20} {want:14} {local:14} {gh:14} {t['url']}{'' if ok else '   <-- MISMATCH'}")
    print("OK" if not bad else f"{bad} mismatches")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    p = sub.add_parser("pack")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--only", nargs="*", choices=list(ARCHIVES))
    p.add_argument("--drop-encrypted", action="store_true", help="replace encrypted reasoning blobs by a placeholder")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--skip-runs", nargs="*", default=[], metavar="PATTERN",
                   help="regular expressions for runs still in progress (left out and listed in the manifest)")
    p.add_argument("--keep-own-history", action="store_true",
                   help="keep tool results that showed this project's own git history (withheld by default)")
    p.add_argument("--base", default=None, metavar="DIR",
                   help="an earlier release: copy its archives unchanged and pack only the files it does not hold")
    p = sub.add_parser("notes", help="(re)write RELEASE_NOTES.md from an existing MANIFEST.json")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p = sub.add_parser("licences")
    p.add_argument("--github", action="store_true", help="also ask GitHub's API (needs the gh command)")
    a = ap.parse_args()
    if a.cmd == "plan":
        tasks = task_table()
        files, skipped = plan()
        for name, members in files.items():
            units = collections.Counter(u for _, _, u in members)
            print(f"{name}: {len(members)} files in {len(units)} runs/folders")
            for u, c in units.items():
                print(f"    {u}: {c}")
        print("not packed:", ", ".join(f"{s['run']} ({s['files']}, {s['why']})" for s in skipped))
        withheld = sorted(t for t, v in tasks.items() if v["rule"] == "withheld")
        print("repositories whose contents are withheld (no licence):", ", ".join(withheld))
    elif a.cmd == "pack":
        if a.base:
            if a.only or a.drop_encrypted or a.keep_own_history or a.skip_runs:
                raise SystemExit("--base takes no other packing option")
            pack_onto(Path(a.base), Path(a.out), a.workers)
        else:
            pack(Path(a.out), a.only, a.drop_encrypted, a.workers, a.keep_own_history, a.skip_runs)
    elif a.cmd == "notes":
        m = json.loads((Path(a.out) / "MANIFEST.json").read_text())
        (Path(a.out) / "RELEASE_NOTES.md").write_text(release_notes(m))
        print((Path(a.out) / "RELEASE_NOTES.md").read_text())
    elif a.cmd == "licences":
        sys.exit(check_licences(a.github))


if __name__ == "__main__":
    main()
