"""Markdown table of the 22-model analysis of the six standard repositories (results/real/panel22.json, written by
`python -m sfe.real_analyze --runs <every real_* and real2_* run> --out panel22`), for an internal report (not published).

    python3 pod/panel22_table.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sfe.real_analyze import NAMES  # noqa: E402

NEW = {"musespark", "dsv4pro", "dsv4flash", "qwen36", "qwen38", "luna6", "terra61", "hydrogen"}
d = json.loads((ROOT / "results" / "real" / "panel22.json").read_text())


def gap(g):
    if not g:
        return "n/a"
    ci = f" ({g['ci'][0]:+.1f} to {g['ci'][1]:+.1f})" if g.get("ci") else ""
    return f"{g['gap']:+.1f}{ci}"


print("| model | episodes analysed (blocked) | changed the attack-like core code: safety / product | left it alone: told the user with a reason / without / not told | reasoning states the decision (safety) | checklist gap, attack-like | checklist gap, measurement | stated chance of a test |")
print("|---|---|---|---|---|---|---|---|")
for m, r in d.items():
    if "conduct" not in r:
        continue
    cs, cc = r["conduct"]["safety"], r["conduct"]["capabilities"]
    cat = cs["categories"]
    told = (f"{cat.get('left it alone, said so with a reason', 0)} / {cat.get('left it alone, said so without a reason', 0)} / "
            f"{cat.get('left it alone, never said so', 0)}")
    pt = r["p_test"]["mean"]
    name = NAMES.get(m, m) + (" (new)" if m in NEW else "")
    print(f"| {name} | {r['n_analysed']} ({r['n_blocked']}) | {cs['core_changed']} of {cs['n']} / {cc['core_changed']} of {cc['n']} | {told} | "
          f"{cs['reasoning_states_decision']} of {cs['n']} | {gap(r.get('done|attack-building'))} | {gap(r.get('done|measurement'))} | "
          f"{'n/a' if pt is None else f'{pt:.0f}%'} |")
