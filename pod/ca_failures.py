"""List the ControlArena tests that fail or error on an untouched checkout, run as an agent user (13 Nov 2026 parity check).
Usage: python pod/ca_failures.py <user or ''> <output file>"""
import json, shutil, subprocess, sys
from pathlib import Path
import sfe.real as real
t = json.loads(Path("real_tasks_new/control_arena/task.json").read_text()); t["id"] = "control_arena"
user = sys.argv[1] or None
ws, repo, base = real.make_checkout(t, "use_monitor_side", user)
sb = real.RealSandbox(repo, ws, real.ensure_venv(t), ".", user)
r = subprocess.run(t["test_cmd"] + " -rfE", shell=True, cwd=repo, env=sb._env(), capture_output=True, text=True, timeout=900,
                   **real.as_sandbox_user(user))
lines = sorted(l.split(" - ")[0] for l in r.stdout.splitlines() if l.startswith(("FAILED ", "ERROR ")))
Path(sys.argv[2]).write_text("\n".join(lines) + "\n" + "SUMMARY " + r.stdout.strip().splitlines()[-1] + "\n")
print(len(lines), r.stdout.strip().splitlines()[-1])
shutil.rmtree(ws)
real.clean_shared_tmp(user=user)
