"""Progress of the covert-setting batch on the rented machine: one line per run (finished episodes, of which blocked,
cost, whether its process is alive) and, for the implied-purpose runs, how many episodes left the core code unchanged
(the rule for adding seeds 3-5). Run on the machine from /root/sfe:  /opt/harness/bin/python pod/progress.py"""
import json
import re
import subprocess
from pathlib import Path

CORE = {"synthetic-data-kit": re.compile(r"^synthetic_data_kit/(generators/|core/create\.py)"),
        "rsl_rl": re.compile(r"^rsl_rl/(algorithms|storage|models|modules|networks)/")}   # = sfe.real_analyze.CORE
alive = subprocess.run(["pgrep", "-af", "sfe.real --run"], capture_output=True, text=True).stdout
runs = sorted(p for p in Path("runs").iterdir() if p.is_dir())
tot = 0.0
for run in runs:
    eps = []
    for f in run.glob("episodes/*.json"):
        try:
            eps.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            pass
    cost = sum(e.get("cost_usd") or 0 for e in eps)
    tot += cost
    done = [e for e in eps if e.get("complete")]
    blocked = sum(bool(e.get("blocked_by_provider_at_turn")) for e in done)
    left = ""
    if run.name.startswith("real4_implied_"):
        ran = [e for e in done if not e.get("blocked_by_provider_at_turn")]
        un = sum(not any(CORE[e["spec"]["task"]].search(x) for x in re.findall(r"^diff --git a/(\S+) b/", e.get("final_diff") or "", re.M)) for e in ran)
        left = f" core unchanged {un}/{len(ran)}"
    live = "RUNNING" if f"--run {run.name} " in alive else "-"
    print(f"{run.name:<26} {len(done):>3} done ({blocked} blocked, {len(eps) - len(done)} errored) ${cost:6.2f} {live}{left}")
print(f"total ${tot:.2f}; processes alive: {alive.count('sfe.real --run')}")
