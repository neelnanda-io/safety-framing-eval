"""Pick illustrative turn-final messages from runs for the results page.

    python -m sfe.examples main_astra main_sol main_astra_careful --out results/examples.json
Picks every turn the judge did not label "worked" (stopping, refusals), every turn flagged for hedging or a
disclosed limitation, plus one ordinary "worked" message per framing for contrast.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sfe.config import RUNS_DIR


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("runs", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--max-per-kind", type=int, default=6)
    a = p.parse_args()
    picked, counts = [], {}
    ordinary = {}
    for run in a.runs:
        for f in sorted((RUNS_DIR / run / "episodes").glob("*.json")):
            r = json.loads(f.read_text())
            s = r["spec"]
            for t in r.get("turns", []):
                j = t.get("judge", {})
                cat = j.get("category", "unknown")
                kinds = []
                if cat not in ("worked", "unknown"):
                    kinds.append(cat)
                if j.get("hedging"):
                    kinds.append("hedging")
                if j.get("disclosed_limitation"):
                    kinds.append("disclosed_limitation")
                meta = (f"{s['model']} · {s['task']} · {s['framing']} · seed {s['seed']} · turn {t['turn']} · "
                        f"{t['grade']['n_pass']}/{t['grade']['n_total']} items · {t['n_tool_calls']} calls"
                        + (" · budget cut" if t.get("hit_budget") else "") + (f" · system={s['system']}" if s.get("system") != "default" else ""))
                for k in kinds:
                    if counts.get(k, 0) < a.max_per_kind:
                        counts[k] = counts.get(k, 0) + 1
                        picked.append({"label": f"{k.replace('_', ' ')} (judge: {j.get('reason', '')[:140]})", "meta": meta,
                                       "text": t["final_text"][:2500]})
                if cat == "worked" and not kinds and s["framing"] not in ordinary and t["turn"] == 1:
                    ordinary[s["framing"]] = {"label": f"ordinary turn, {s['framing']} framing", "meta": meta, "text": t["final_text"][:2500]}
    picked += list(ordinary.values())
    Path(a.out).write_text(json.dumps(picked, indent=1))
    print(f"picked {len(picked)} examples: {counts}")


if __name__ == "__main__":
    main()
