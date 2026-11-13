"""Merge episodes pulled from the rented machine (runs_pod/runs) into runs/. Stand-in files are ignored; a finished cloud
episode replaces a local file only when the local one is missing or unfinished."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
new = kept = stubs = unfinished = 0
for f in sorted((ROOT / "runs_pod" / "runs").glob("*/episodes/*.json")):
    try:
        r = json.loads(f.read_text())
    except json.JSONDecodeError:
        continue                      # still being written
    if r.get("stub"):
        stubs += 1
        continue
    if not r.get("complete"):
        unfinished += 1
        continue
    dest = ROOT / "runs" / f.relative_to(ROOT / "runs_pod" / "runs")
    if dest.exists():
        try:
            if json.loads(dest.read_text()).get("complete"):
                kept += 1
                continue
        except json.JSONDecodeError:
            pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(f, dest)
    new += 1
print(f"merged {new} new episodes from the cloud machine ({kept} already here, {stubs} stand-ins, {unfinished} unfinished or errored)")
