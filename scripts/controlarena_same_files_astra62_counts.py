"""Mechanical counts for docs/CONTROLARENA_SAME_FILES_ASTRA62_PREREG.md (18 Nov 2026): GPT-6.2 Astra on ControlArena under the
two descriptions that name the same attack-side files (files_evasion, files_upkeep), seeds 0 to 3, run
new_control_files_astra62. Writes results/real/controlarena_same_files_astra62_runs.json.

Per episode: complete, blocked by a provider's filter, changed no file, whether the named attack-side files were changed
(the attack-side rule CORE["control_arena"] through sfe/core_code.py, via sfe.new_repos.core_facts, as in
results/real/controlarena_same_files.json), which of them, whether a monitor file changed, how many tool calls opened one of
the named files (each call read in full), files changed, cost, providers, and the stated chance of a test read from the second
closing answer by sfe.closing_answers.stated_chance (no model call). A second route (core_files on the final diff with
CORE["control_arena"] directly) must agree. Rule C1, what the user was told and the Result are NOT here.

    python3 scripts/controlarena_same_files_astra62_counts.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfe.closing_answers import stated_chance  # noqa: E402
from sfe.core_code import core_files, core_pattern  # noqa: E402
from sfe.new_repos import CORE, core_facts  # noqa: E402

RUN = "new_control_files_astra62"
DESCRIPTIONS = ["files_evasion", "files_upkeep"]
SEEDS = range(4)
OUT = ROOT / "results" / "real" / "controlarena_same_files_astra62_runs.json"


def row(path: Path) -> dict:
    r = json.loads(path.read_text())
    sp = r["spec"]
    assert core_pattern("control_arena", sp["framing"]) == CORE["control_arena"], sp["framing"]
    f = core_facts(r)
    diff = r.get("final_diff") or ""
    assert bool(core_files(diff, CORE["control_arena"])) == f["core_changed"], r["id"]
    blocked = bool(r.get("blocked_by_provider_at_turn")) or any(t.get("filter_blocked") for t in r.get("turns", []))
    d = r.get("debrief") or {}
    return {"run": RUN, "id": r["id"], "model": "astra62", "model_name": "GPT-6.2 Astra", "description": sp["framing"],
            "seed": sp["seed"], "path": str(path.relative_to(ROOT)), "complete": bool(r.get("complete")),
            "error": (r.get("error") or "")[:200] or None, "blocked_by_provider": blocked,
            "filter_refusals": sum(t.get("filter_refusals", 0) for t in r.get("turns", [])),
            "turns": len(r.get("turns", [])), "tool_calls_per_turn": [t.get("n_tool_calls", 0) for t in r.get("turns", [])],
            "changed_no_file": not f["files"], "files_changed": len(f["files"]),
            "named_part_changed": f["core_changed"], "named_part_files_changed": f["core_files"],
            "opened_named_part_calls": f["core_opened"],
            "monitor_files_changed": [x for x in f["files"] if x.startswith("control_arena/monitor/")],
            "folders": f["folders"], "lines_named_part": f["lines_core"], "lines_elsewhere": f["lines_elsewhere"],
            "stated_chance_of_test": stated_chance(d.get("test_prob") or "") if d.get("test_prob") else None,
            "closing_answers": bool(d.get("setting") and d.get("test_prob") and not d.get("error")),
            "cost_usd": round(r.get("cost_usd") or 0, 4), "minutes": round((r["finished"] - r["started"]) / 60, 1),
            "providers": dict(Counter(p for t in r.get("turns", []) for p in (t.get("providers") or []))),
            "paid_through_own_key": any(t.get("is_byok") for t in r.get("turns", [])),
            "tmp_seeded": r.get("tmp_seeded"), "sandbox_user": r.get("sandbox_user"), "platform": r.get("platform")}


def main() -> None:
    rows, missing = [], []
    for desc in DESCRIPTIONS:
        for s in SEEDS:
            p = ROOT / "runs" / RUN / "episodes" / f"astra62__control_arena__{desc}__s{s}.json"
            (rows.append(row(p)) if p.exists() else missing.append(p.name))
    table = {}
    for desc in DESCRIPTIONS:
        rs = [x for x in rows if x["description"] == desc]
        table[desc] = {"episodes": len(rs), "complete": sum(x["complete"] for x in rs),
                       "blocked_by_provider": sum(x["blocked_by_provider"] for x in rs),
                       "changed_no_file": sum(x["changed_no_file"] for x in rs),
                       "named_part_changed": sum(x["named_part_changed"] for x in rs),
                       "named_part_left_alone_of_those_that_changed_some_file": [
                           sum(not x["named_part_changed"] for x in rs if x["complete"] and not x["blocked_by_provider"]
                               and not x["changed_no_file"]),
                           sum(1 for x in rs if x["complete"] and not x["blocked_by_provider"] and not x["changed_no_file"])],
                       "cost_usd": round(sum(x["cost_usd"] for x in rs), 2)}
    out = {"about": ("Mechanical counts for docs/CONTROLARENA_SAME_FILES_ASTRA62_PREREG.md (commit fc9776d): GPT-6.2 Astra, "
                     "ControlArena, files_evasion and files_upkeep, seeds 0-3. Named part = the attack-side rule "
                     "CORE['control_arena'] through sfe/core_code.py (test files never count), as in "
                     "results/real/controlarena_same_files.json. Stated chance by sfe.closing_answers.stated_chance. Rule C1, "
                     "what the user was told and the Result are not applied here. Script: "
                     "scripts/controlarena_same_files_astra62_counts.py."),
           "missing": missing, "table": table, "cost_usd": round(sum(x["cost_usd"] for x in rows), 2), "rows": rows}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(rows)} episodes read, {len(missing)} missing; wrote {OUT.relative_to(ROOT)}")
    for desc, c in table.items():
        print(f"  {desc}: {c}")
    for x in rows:
        print(f"  {x['id']}: named part changed {x['named_part_changed']} {x['named_part_files_changed']}, opened "
              f"{x['opened_named_part_calls']}, files {x['files_changed']}, monitor {x['monitor_files_changed']}, "
              f"${x['cost_usd']:.2f}, chance {x['stated_chance_of_test']}")


if __name__ == "__main__":
    main()
