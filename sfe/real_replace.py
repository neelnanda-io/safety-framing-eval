"""Set aside the episodes that sfe.real_screen found spoiled, so that clean re-runs can take their place.

For every episode in results/real/exclusions.json this moves the episode file to runs/<run>/replaced/, moves its staging
copy and its checklist grades out of the way, and drops its disclosure label and closing-answer label (all of which are
keyed by episode id and would otherwise attach to the re-run). What was set aside and why is appended to
results/real/replaced_episodes.json, with the old episode's headline numbers. Safe to run twice.

    python -m sfe.real_replace
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from sfe.config import RESULTS_DIR, ROOT, RUNS_DIR
from sfe.real_analyze import core_touched


def main() -> None:
    real = RESULTS_DIR / "real"
    excl = json.loads((real / "exclusions.json").read_text())
    log_path = real / "replaced_episodes.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {}
    disc_path, scored_path = real / "disclosure_labels.json", RESULTS_DIR / "debrief" / "scored.json"
    disc = json.loads(disc_path.read_text()) if disc_path.exists() else {}
    scored = json.loads(scored_path.read_text()) if scored_path.exists() else []
    moved = 0
    for key, e in excl.items():
        run, eid = key.split("__", 1)
        src = RUNS_DIR / run / "episodes" / f"{eid}.json"
        if not src.exists():
            continue
        r = json.loads(src.read_text())
        grade = real / "grades" / "argon" / f"{key}.json"
        g = json.loads(grade.read_text()) if grade.exists() else {}
        log[key] = {**e, "set_aside_at": time.strftime("%Y-%m-%d %H:%M:%S"), "old_started": r.get("started"),
                    "old_checklist_done_pct": round(100 * g["done"] / g["n_items"], 1) if g else None,
                    "old_core_changed": core_touched(r["spec"]["task"], r.get("final_diff", "")),
                    "old_diff_lines": len((r.get("final_diff") or "").splitlines()), "old_cost_usd": r.get("cost_usd")}
        dest = RUNS_DIR / run / "replaced" / f"{eid}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        stage = ROOT / "runs_pod" / "runs" / run / "episodes" / f"{eid}.json"
        if stage.exists():
            sd = ROOT / "runs_pod" / "replaced" / run / f"{eid}.json"
            sd.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(stage), str(sd))
        for jd in (real / "grades").iterdir():
            gf = jd / f"{key}.json"
            if jd.is_dir() and not jd.name.endswith("_replaced") and gf.exists():
                gd = real / "grades" / f"{jd.name}_replaced" / gf.name
                gd.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(gf), str(gd))
        disc.pop(key, None)
        scored = [x for x in scored if not (x.get("run") == run and x.get("episode") == eid)]
        moved += 1
        print(f"set aside {key}: " + "; ".join(e["why"])[:150])
    log_path.write_text(json.dumps(log, indent=1))
    disc_path.write_text(json.dumps(disc, indent=1))
    scored_path.write_text(json.dumps(scored, indent=1))
    print(f"{moved} episodes set aside; {len(log)} listed in {log_path}")


if __name__ == "__main__":
    main()
