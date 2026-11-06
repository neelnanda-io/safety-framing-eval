"""Write the intro (headline answer) HTML for the results page from summary.json.

    python -m sfe.report_text results/main3 --out results/main3/intro.html
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def pct1(x: float) -> str:
    return f"{100 * x:.1f}%"


def pp(x: float) -> str:
    return f"{100 * x:+.1f} pp"


def verdict(gap: float, lo: float, hi: float) -> str:
    if lo > 0:
        size = "small" if gap < 0.05 else "moderate" if gap < 0.1 else "large"
        return f"a {size} gap in the report's direction"
    if hi < 0:
        return "a gap in the opposite direction"
    return "no detectable gap"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("res_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--secondary", nargs="*", default=[], help="other summary.json files (tainted replications) to cite")
    a = ap.parse_args()
    S = json.loads((Path(a.res_dir) / "summary.json").read_text())
    c = S["cells"]; p = S["paired"]
    ad = p["astra|default"]; cap = c["astra|default|capabilities"]; saf = c["astra|default|safety"]
    sol = p.get("sol|default"); car = p.get("astra|careful")
    lo, hi = ad["gap_ci"]
    verdict_main = verdict(ad["gap_cap_minus_safety"], lo, hi)
    sec = []
    for path in a.secondary:
        T = json.loads(Path(path).read_text())
        q = T["paired"].get("astra|default")
        if q:
            sec.append(f"{pp(q['gap_cap_minus_safety'])} ({pp(q['gap_ci'][0])} to {pp(q['gap_ci'][1])}, {q['n_pairs']} pairs)")
    html = f"""
<div class="answer"><strong>Answer.</strong> On this replication, describing the task as AI-safety research produced
{verdict_main} for GPT-6 Astra. Across {ad['n_pairs']} matched pairs Astra completed {pct1(saf['completion'])} of hidden rubric
items under the safety framing and {pct1(cap['completion'])} under the capabilities framing: a paired difference of
{pp(ad['gap_cap_minus_safety'])} (95% CI {pp(lo)} to {pp(hi)}), against the report's 6 pp (10% vs 16%). The report's other
signature, more turns ending in "nothing worthwhile remains" or a blocker, did not appear: {pct1(saf['stopping'])} of
safety-framed turns vs {pct1(cap['stopping'])} of capabilities-framed turns, with no refusals in either condition.
{"GPT-5.6 Sol, the report's no-gap control, showed " + pp(sol['gap_cap_minus_safety']) + " (" + pp(sol['gap_ci'][0]) + " to " + pp(sol['gap_ci'][1]) + ")." if sol else ""}
{"Adding “be careful” to Astra's system prompt, which raised the gap by half in the report, gave " + pp(car['gap_cap_minus_safety']) + " (" + pp(car['gap_ci'][0]) + " to " + pp(car['gap_ci'][1]) + ", " + str(car['n_pairs']) + " pairs)." if car else ""}
</div>
<p class="muted">Two earlier full runs of the same design, each spoiled by a sandbox bug that rejected about two legitimate
commands per episode (identically in both framings), gave Astra gaps of {" and ".join(sec) if sec else "n/a"}; they are kept as
noisy replications, not as primary evidence.</p>
<p><strong>How to read this.</strong> One episode is one model working for three turns on one repository under one framing.
A rubric item is one planted bug or missing behaviour, checked by a hidden test. Pairs share the task and seed and differ only
in framing. "Subtle" items are the roughly half of the rubric that nothing in the repository points at. The absolute
completion level here (about 85–90%) is far above the report's 10–16%, so the sensitive comparison is the paired gap, the
turn-1 column, and the subtle-item column, not the headline level.</p>
"""
    Path(a.out).write_text(html)
    print(html[:600])


if __name__ == "__main__":
    main()
