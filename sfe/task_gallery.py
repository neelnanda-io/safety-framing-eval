"""HTML fragment showing every task: blurbs, a side-by-side of differing lines between the safety and capabilities
renderings, file sizes, and sample rubric items by tier.

    python -m sfe.task_gallery --out results/task_gallery.html [--tasks ...]
"""
from __future__ import annotations

import argparse
import difflib
import html
import tempfile
from pathlib import Path

from sfe.render import list_tasks, load_task, render_task


def esc(s):
    return html.escape(s)


def section(task_id: str) -> str:
    t = load_task(task_id)
    tmp = Path(tempfile.mkdtemp(prefix="gallery_"))
    rs, rc = render_task(t, "safety", tmp / "s"), render_task(t, "capabilities", tmp / "c")
    files_s = sorted(p.relative_to(rs) for p in rs.rglob("*") if p.is_file())
    files_c = sorted(p.relative_to(rc) for p in rc.rglob("*") if p.is_file())
    n_lines = sum(len((rs / p).read_bytes().splitlines()) for p in files_s)
    tiers = {}
    for r in t.rubric:
        tiers.setdefault(r.get("tier", "obvious"), []).append(r)
    # side-by-side differing lines from the main source files (first 14 differing pairs)
    pairs = []
    for ps, pc in zip(files_s, files_c):
        if ps.suffix != ".py" or "test" in str(ps):
            continue
        a = (rs / ps).read_text().splitlines(); b = (rc / pc).read_text().splitlines()
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y and x.strip():
                pairs.append((str(ps), i + 1, x.strip(), str(pc), y.strip()))
    pairs = pairs[:14]
    rows = "".join(f"<tr><td class='ln'>{esc(ps)}:{ln}</td><td><code>{esc(x[:110])}</code></td><td><code>{esc(y[:110])}</code></td></tr>"
                   for ps, ln, x, pc, y in pairs)
    sample = []
    for tier in ("obvious", "subtle", "deep"):
        for r in tiers.get(tier, [])[:4]:
            sample.append(f"<li><span class='tier tier-{tier}'>{tier}</span> {esc(r['desc'])}</li>")
    counts = ", ".join(f"{len(v)} {k}" for k, v in tiers.items())
    blurbs = "".join(f"<p class='blurb'><strong>{fr}.</strong> {esc(t.framings[fr]['TASK_BLURB'])}</p>" for fr in ("safety", "capabilities", "neutral"))
    return f"""<details class='task'><summary><code>{esc(task_id)}</code> — {esc(t.meta.get('title', ''))}
<span class='muted'>· {len(files_s)} files, {n_lines} lines · {len(t.rubric)} rubric items ({counts}) · boundary {esc(str(t.meta.get('boundary')))}</span></summary>
{blurbs}
<h5>Lines that differ between the two renderings (first {len(pairs)})</h5>
<div class='tablewrap'><table><thead><tr><th>where</th><th>safety rendering</th><th>capabilities rendering</th></tr></thead><tbody>{rows}</tbody></table></div>
<h5>Sample rubric items</h5><ul>{''.join(sample)}</ul></details>"""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--tasks", nargs="*")
    a = ap.parse_args()
    ids = a.tasks or list_tasks()
    css = """<style>.task{margin:10px 0}.blurb{font-size:14px;margin:6px 0}.ln{color:var(--muted);font-size:12px;white-space:nowrap}
.tier{display:inline-block;font-size:11px;padding:1px 6px;border-radius:10px;border:1px solid var(--rule);margin-right:6px;color:var(--muted)}
.tier-deep{border-color:var(--saf)} .tier-subtle{border-color:var(--cap)} h5{margin:12px 0 4px;font-size:13px}</style>"""
    Path(a.out).write_text(css + "".join(section(t) for t in ids))
    print("wrote", a.out, len(ids), "tasks")


if __name__ == "__main__":
    main()
