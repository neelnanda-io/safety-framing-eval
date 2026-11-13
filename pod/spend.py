"""Spend of the covert-setting batch by part, summed from the saved episode files copied from the rented machine
(runs_pod/runs, the staging copy pod/pull.sh keeps). Never inferred from the account balance (other work shares it).

    python3 pod/spend.py
"""
import glob
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEW = ["musespark", "dsv4pro", "dsv4flash", "qwen36", "qwen38", "luna6", "terra61", "hydrogen"]
CAPS = {"S1": 200, "S2": 280, "S3": 130, "S4": 130}


def part(run: str):
    if run in {f"real2_{m}" for m in NEW}:
        return "S1"
    if run.startswith("real4_implied_"):
        return "S2"
    if run.startswith("new_control_"):
        return "S3"
    if run.startswith("new_generic4_"):
        return "S4"
    return None


tot, n, unfinished = defaultdict(float), defaultdict(int), defaultdict(int)
by_run = defaultdict(float)
for f in glob.glob(str(ROOT / "runs_pod" / "runs" / "*" / "episodes" / "*.json")):
    run = Path(f).parts[-3]
    p = part(run)
    if not p:
        continue
    try:
        r = json.loads(Path(f).read_text())
    except json.JSONDecodeError:
        continue
    if r.get("stub"):
        continue
    tot[p] += r.get("cost_usd") or 0
    by_run[run] += r.get("cost_usd") or 0
    n[p] += 1
    unfinished[p] += not r.get("complete")
for p in ("S1", "S2", "S3", "S4"):
    print(f"{p}: ${tot[p]:7.2f} of ${CAPS[p]} cap, {n[p]} episode files ({unfinished[p]} not complete)")
print("by run:", ", ".join(f"{k} ${v:.2f}" for k, v in sorted(by_run.items(), key=lambda kv: -kv[1])))
