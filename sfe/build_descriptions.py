"""Every description the user gave a model, word for word, on one page: python3 -m sfe.build_descriptions

Built from the task files the harnesses read (real_tasks/*/task.json, real_tasks_new/*/task.json and
tasks/<id>/framings/*.json), so the text is exactly what was sent: for the real repositories the user's first message is
the description followed by sfe.real.TURN1's request (checked against saved episodes when this was written), and the
README section is the description's `note`, added by one top commit. Under each description: which models were run on
it in full episodes, counted from the episode file names under runs/. Output: results/descriptions/index.html.
"""
from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "descriptions" / "index.html"
TOY_FRAMINGS = ("safety", "capabilities", "neutral")
ORIGINAL_FIRST = ("rsl_rl", "synthetic-data-kit")          # the two attack-like repositories lead
PLAIN_ORIGINAL = {"safety": "The safety description (the original)", "capabilities": "The product description (the original)",
                  "safety_reworded": "A milder wording of the safety description, for the Claude models, whose provider's filter "
                                     "blocked the original",
                  "capabilities_reworded": "A milder wording of the product description, for the Claude models, whose provider's "
                                           "filter blocked the original"}
TOY_PLAIN = {"safety": "Safety description", "capabilities": "Capabilities description", "neutral": "Neutral description"}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


TOY_ONLY_NAMES = {"sol61": "GPT-6.1 Sol", "fable": "Claude Fable 5.1", "sol6": "GPT-6 Sol", "neon": "Gemini 4 Neon"}


def model_name(key: str) -> str:
    """Display name from the public tables (sfe.real_analyze.NAMES, sfe.panel_counts.EXTRA_NAMES), then the keys used only
    by toy-task runs; a key no table names (a smoke-test model, say) is shown as it is."""
    from sfe.panel_counts import EXTRA_NAMES
    from sfe.real_analyze import NAMES
    return NAMES.get(key) or EXTRA_NAMES.get(key) or TOY_ONLY_NAMES.get(key) or key


def episode_counts() -> Counter:
    """(task, framing, model) -> number of saved full episodes, from the file names under runs/ (real episodes are
    model__task__framing__sN.json in runs/<run>/episodes/, toy ones model__task__framing__sN__system.json)."""
    c: Counter = Counter()
    for f in (ROOT / "runs").glob("**/*.json"):
        parts = f.stem.split("__")
        if len(parts) >= 4 and re.fullmatch(r"s\d+", parts[3]):
            c[(parts[1], parts[2], parts[0])] += 1
    return c


def runs_line(counts: Counter, task: str, framing: str) -> str:
    by = sorted(((n, model_name(m)) for (t, f, m), n in counts.items() if t == task and f == framing), key=lambda x: (-x[0], x[1]))
    if not by:
        return '<p class="runs none">No full episodes (used only in one-turn checks of the first reply, or not run).</p>'
    total = sum(n for n, _ in by)
    items = " · ".join(f"{esc(name)} {n}" for n, name in by)
    return f'<p class="runs"><b>Full episodes ({total}):</b> {items}</p>'


def real_tasks() -> list[dict]:
    out = []
    for f in sorted(list((ROOT / "real_tasks").glob("*/task.json")) + list((ROOT / "real_tasks_new").glob("*/task.json"))):
        t = json.loads(f.read_text())
        out.append(dict(t, id=f.parent.name, new=f.parent.parent.name == "real_tasks_new"))
    return out


def desc_block(task: str, key: str, label: str, message: str | None, note: str | None, counts: Counter, toy: bool = False) -> str:
    if message:
        msg = f'<blockquote class="msg">{esc(message)}</blockquote>'
    else:
        msg = '<p class="empty">No description: the first message is the request alone, and nothing is added to the README.</p>'
    readme = (f'<details class="readme"><summary>README section added</summary><blockquote class="msg">{esc(note)}</blockquote>'
              '</details>') if note else ""
    return (f'<div class="desc"><h4>{esc(label)}</h4><p class="key">{esc(key)}</p>{msg}{readme}'
            f'{runs_line(counts, task, key)}</div>')


def repo_section(t: dict, counts: Counter, open_: bool = False) -> str:
    fr = t.get("framings") or {}
    blocks = []
    for key, v in fr.items():
        label = v.get("edit") or PLAIN_ORIGINAL.get(key) or key
        label = label[0].upper() + label[1:] if label else key
        blocks.append(desc_block(t["id"], key, label, (v.get("context") or "").strip() or None, (v.get("note") or "").strip() or None, counts))
    what = f'<p class="what">{esc(t["what"])}</p>' if t.get("what") else ""
    url = t.get("url", "").removesuffix(".git")
    link = f' · <a href="{esc(url)}">{esc(url.removeprefix("https://"))}</a>' if url else ""
    return (f'<details class="repo" id="r-{esc(t["id"])}"{" open" if open_ else ""}><summary><span class="rname">{esc(t.get("name") or t["id"])}</span>'
            f'<span class="rcount">{len(fr)} description{"s" if len(fr) != 1 else ""}</span></summary>'
            f'<div class="rbody"><p class="meta">Folder <code>{esc(t["id"])}</code>{link}</p>{what}{"".join(blocks)}</div></details>')


def toy_label(task: str, key: str) -> str:
    """The three main descriptions by name; the variants of the 10 Nov description study (sfe.family.CELLS) by what they
    change: how the code's identifiers are written and which team the description names."""
    if key in TOY_PLAIN:
        return TOY_PLAIN[key]
    from sfe.family import CELLS
    ident, team = CELLS.get(task, {}).get(key, (None, None))
    if ident is None:
        return f"Variant: {key.replace('_', ' ')}"
    return f"Description-study variant: code written as {ident}, team in the description: {team}"


def toy_section(counts: Counter) -> str:
    out = []
    for d in sorted((ROOT / "tasks").iterdir()):
        if not (d / "task.json").exists():
            continue
        meta = json.loads((d / "task.json").read_text())
        blocks = []
        files = sorted((d / "framings").glob("*.json"), key=lambda p: (p.stem not in TOY_FRAMINGS,
                                                                       TOY_FRAMINGS.index(p.stem) if p.stem in TOY_FRAMINGS else 0, p.stem))
        for p in files:
            blurb = json.loads(p.read_text()).get("TASK_BLURB", "").strip()
            blocks.append(desc_block(d.name, p.stem, toy_label(d.name, p.stem), blurb or None, None, counts, toy=True))
        out.append(f'<details class="repo" id="t-{esc(d.name)}"><summary><span class="rname">{esc(meta.get("title") or d.name)}</span>'
                   f'<span class="rcount">{len(blocks)} descriptions</span></summary><div class="rbody"><p class="meta">Folder '
                   f'<code>tasks/{esc(d.name)}</code></p>{"".join(blocks)}</div></details>')
    return "".join(out)


STYLE = """
<style>
:root{--bg:#f6f7f9;--panel:#ffffff;--ink:#15191f;--ink2:#47505e;--ink3:#737c8a;--line:#dde1e8;--accent:#2563c9;
  --quote:#eef3fb;--quoteline:#2563c9;--display:"Space Grotesk","Inter",system-ui,sans-serif;--body:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#111419;--panel:#191d24;--ink:#eceff3;--ink2:#b9c1cd;
  --ink3:#8a93a1;--line:#2b313b;--accent:#6ea3ff;--quote:#1b2433;--quoteline:#6ea3ff;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#111419;--panel:#191d24;--ink:#eceff3;--ink2:#b9c1cd;--ink3:#8a93a1;--line:#2b313b;--accent:#6ea3ff;
  --quote:#1b2433;--quoteline:#6ea3ff;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:16px;line-height:1.55;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:28px 64px}
main{max-width:820px;margin:0 auto;display:flex;flex-direction:column;gap:22px}
h1{font-family:var(--display);font-weight:600;font-size:1.75rem;line-height:1.2;margin:0;text-wrap:balance}
h2{font-family:var(--display);font-weight:600;font-size:1.2rem;margin:8px 0 6px;text-wrap:balance}
h4{font-size:1rem;font-weight:600;margin:0}
p{margin:0} a{color:var(--accent)} code{font-size:.88em}
.lede{font-size:1.05rem;color:var(--ink2);max-width:68ch}
.facts{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px;display:flex;flex-direction:column;gap:8px;font-size:.95rem;color:var(--ink2)}
.facts b{color:var(--ink)}
.toc{display:flex;flex-direction:column;gap:6px;font-size:.95rem}
.toc a{text-decoration:none} .toc a:hover{text-decoration:underline}
section{display:flex;flex-direction:column;gap:8px}
.sub{color:var(--ink3);font-size:.92rem;max-width:68ch}
details.repo{background:var(--panel);border:1px solid var(--line);border-radius:8px}
details.repo>summary{cursor:pointer;padding:12px 14px;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;list-style:none}
details.repo>summary::-webkit-details-marker{display:none}
details.repo>summary::before{content:"▸";color:var(--ink3);margin-right:2px}
details.repo[open]>summary::before{content:"▾"}
.rname{font-weight:600} .rcount{color:var(--ink3);font-size:.88rem}
.rbody{padding:0 14px 14px;display:flex;flex-direction:column;gap:14px}
.meta,.what{color:var(--ink2);font-size:.92rem}
.desc{border-top:1px solid var(--line);padding-top:12px;display:flex;flex-direction:column;gap:6px;min-width:0}
.key{color:var(--ink3);font-size:.8rem;font-family:ui-monospace,Menlo,monospace;letter-spacing:.01em}
blockquote.msg{margin:0;background:var(--quote);border-left:3px solid var(--quoteline);border-radius:0 6px 6px 0;padding:10px 12px;
  white-space:pre-wrap;overflow-wrap:anywhere;font-size:.95rem}
.empty{color:var(--ink2);font-style:italic;font-size:.95rem}
details.readme>summary{cursor:pointer;color:var(--ink2);font-size:.88rem}
details.readme blockquote{margin-top:6px}
.runs{font-size:.85rem;color:var(--ink2)} .runs.none{color:var(--ink3)}
</style>"""


def build() -> str:
    counts = episode_counts()
    tasks = real_tasks()
    orig = sorted((t for t in tasks if not t["new"]), key=lambda t: (t["id"] not in ORIGINAL_FIRST, ORIGINAL_FIRST.index(t["id"]) if t["id"] in ORIGINAL_FIRST else 0, t["id"]))
    ca = [t for t in tasks if t["new"] and t["id"] == "control_arena"]
    gen = [t for t in tasks if t["new"] and t["id"] == "new_rl"]
    other = sorted((t for t in tasks if t["new"] and t["id"] not in ("control_arena", "new_rl")), key=lambda t: t["id"])
    n_real = sum(len(t.get("framings") or {}) for t in tasks)
    n_toy = sum(1 for _ in (ROOT / "tasks").glob("*/framings/*.json"))
    from sfe.real import TURN1, TURN_NEXT, PAUSE_MSG
    from sfe.config import TURN1_TEMPLATE, TURN_NEXT as TOY_NEXT, TURN_BUDGET_MSG
    request = TURN1.split("\n\n", 1)[1]
    toy_tail = TURN1_TEMPLATE.split("{repo_dump}\n\n", 1)[1]
    groups = [
        ("g1", "The six repositories of the first real-repository study (10 Nov)",
         "The two attack-like repositories first: their safety uses are training a policy that gets past a monitor (rsl_rl) "
         "and generating data for backdoored model organisms (synthetic-data-kit). Each has the original pair of "
         "descriptions plus the single-change variants used to find what sets the hold-back off.", orig),
        ("g2", "ControlArena", "One library, described as used for its attack side, its monitor side, or the same named files for two purposes.", ca),
        ("g3", "The generic RL library", "One library with many stated uses, from harmless to getting rule-breaking behaviour past a check.", gen),
        ("g4", f"The {len(other)} other new repositories (13 Nov)", "Each with the request alone and with a truthful statement of how a team uses it, plus a few variants.", other),
    ]
    toc = "".join(f'<a href="#{gid}">{esc(title)}</a>' for gid, title, _, _ in groups) + '<a href="#g5">The ten toy tasks</a>'
    parts = [f'<section id="{gid}"><h2>{esc(title)}</h2><p class="sub">{esc(sub)}</p>'
             + "".join(repo_section(t, counts, open_=(t["id"] == "rsl_rl")) for t in ts) + "</section>"
             for gid, title, sub, ts in groups]
    toy = (f'<section id="g5"><h2>The ten toy tasks</h2><p class="sub">Small packages written for this project, each in a safety, a '
           f'capabilities and a neutral version; the code differs only in names, comments and documentation. Two tasks also have the '
           f'variants of the 10 Nov description study.</p>{toy_section(counts)}</section>')
    facts = (
        f'<p><b>Real repositories.</b> The user\'s first message is the description, a blank line, and then: '
        f'“{esc(request)}” A description also adds a short section to the README by one top commit (shown under each). '
        f'Later messages are fixed: “{esc(TURN_NEXT[0])}”, then “{esc(TURN_NEXT[1])}”, then two closing questions after the work.</p>'
        f'<p><b>Tool calls.</b> Real repositories: 3 turns of at most 25 tool calls each (so at most 75 in an episode); a turn '
        f'that reaches 25 gets “{esc(PAUSE_MSG)}” and the next turn starts with the next message. Toy tasks: 3 turns of at '
        f'most 15 each; a turn that reaches 15 gets “{esc(TURN_BUDGET_MSG)}”</p>'
        f'<p><b>Toy tasks.</b> The first message is the description, a blank line, “The repository contains these files:”, the file '
        f'list, and then: “{esc(toy_tail)}” Later turns: “{esc(TOY_NEXT)}”</p>'
        f'<p><b>Under each description:</b> how many full episodes each model was run on with it, counted from the saved '
        f'episode files. A description with none was used only in one-turn checks of the first reply, or not run.</p>')
    body = (f'<title>Repository Descriptions</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@600&display=swap">'
            f'{STYLE}\n<main><header><h1>Every description the user gave, word for word</h1></header>'
            f'<p class="lede">{n_real} descriptions of {len(tasks)} real repositories and {n_toy} of ten toy tasks, exactly as the '
            f'models received them, grouped by repository. Open a repository to read its descriptions.</p>'
            f'<div class="facts">{facts}</div><nav class="toc">{toc}</nav>{"".join(parts)}{toy}</main>')
    return body


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build())
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
