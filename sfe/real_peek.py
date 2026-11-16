"""Print one line per real-repository episode: what the agent did, without needing grades.

    python -m sfe.real_peek --runs real2_opus real2_grok
"""
import argparse
import glob
import json
import re
from pathlib import Path

from sfe.config import RUNS_DIR
from sfe.real_analyze import NAMES, core_opened, core_touched


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--text", action="store_true", help="also print the first 300 characters of each turn's final message")
    a = ap.parse_args()
    print(f"{'model':<20}{'repository':<20}{'description':<13}{'seed':>4} {'calls/turn':<12}{'diff':>6} {'core opened':>12} {'changed':>8} "
          f"{'filter-refused turns':>21} {'test?':>6} {'cost':>6}")
    for run in a.runs:
        for f in sorted(glob.glob(f"{RUNS_DIR}/{run}/episodes/*.json")):
            r = json.loads(Path(f).read_text())
            sp = r["spec"]
            m = re.search(r"(\d{1,3})(?:\s*%| that| percent)", (r.get("debrief") or {}).get("test_prob") or "")
            co, ct = core_opened(sp["task"], r["turns"], r.get("messages") or []), core_touched(sp["task"], r.get("final_diff", ""))
            flag = "" if r.get("complete") else "  INCOMPLETE: " + str(r.get("error"))[:90]
            print(f"{NAMES.get(sp['model'], sp['model']):<20}{sp['task']:<20}{sp['framing']:<13}{sp['seed']:>4} "
                  f"{'/'.join(str(t['n_tool_calls']) for t in r['turns']):<12}{len(r.get('final_diff', '').splitlines()):>6} "
                  f"{'-' if co is None else co:>12} {'-' if ct is None else ('yes' if ct else 'no'):>8} "
                  f"{sum(bool(t.get('platform_refusal')) for t in r['turns']):>21} {(m.group(1) + '%') if m else '-':>6} "
                  f"{r['cost_usd']:>6.2f}{flag}")
            if a.text:
                for t in r["turns"]:
                    print(f"      turn {t['turn']}: {t['final_text'][:300]!r}")


if __name__ == "__main__":
    main()
