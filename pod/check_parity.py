"""Parity check on a rented machine (13 Nov 2026): run each repository's own tests on an untouched checkout, as an agent
user from the pool, and compare the pass/fail counts with the laptop's (the counts every earlier laptop episode recorded).
Also reports whether an agent user can reach the internet. Run as root from /root/sfe with the run environment:

    SFE_SANDBOX_USERS=... SFE_SCRUB_USER= SFE_VENV_BASE=/var/tmp/venvs SFE_BASE_PYTHON=$(cat pod/base_python.txt) \\
        /opt/harness/bin/python pod/check_parity.py
"""
import concurrent.futures as cf
import json
import os
import shutil
import sys
import time
from pathlib import Path

LAPTOP = {"rsl_rl": {"failed": 5, "passed": 182}, "valor": {"failed": 5, "passed": 908, "skipped": 6},
          "prompto": {"failed": 20, "passed": 255}, "synthetic-data-kit": {"passed": 93},
          "NeuroX": {"failed": 5, "passed": 161}, "dictionary_learning": {"failed": 2, "passed": 11},
          "control_arena": {"error": 61, "failed": 110, "passed": 1148, "skipped": 1},
          "new_rl": {"error": 2, "failed": 90, "passed": 125}}     # laptop count for the generic RL library (S4, 13 Nov 2026)
users = os.environ["SFE_SANDBOX_USERS"].split(",")


import sfe.real as real  # noqa: E402


def load(tid, tasks_dir):
    t = json.loads((Path(tasks_dir) / tid / "task.json").read_text())
    t["id"] = tid
    return t


def one(i_t):
    i, t = i_t
    tid = t["id"]
    user = users[i]
    t0 = time.time()
    ws, repo, base = real.make_checkout(t, "capabilities" if "capabilities" in t["framings"] else "use_monitor_side", user)
    sb = real.RealSandbox(repo, ws, real.ensure_venv(t), t.get("pythonpath", "."), user)
    r = sb.baseline_tests(t["test_cmd"])
    who = sb.run_command("whoami; ls -ld . | cut -c1-10").replace("\n", " | ")
    shutil.rmtree(ws)
    real.clean_shared_tmp(user=user)
    same = r.get("counts") == LAPTOP[tid]
    return f"{tid:<20} {'SAME' if same else 'DIFFERENT'} as laptop: {r.get('counts')} (laptop {LAPTOP[tid]}) in {time.time() - t0:.0f}s as {who}"


print("agent can reach the internet:", real.agent_can_reach_internet(), flush=True)
STANDARD = ("rsl_rl", "valor", "prompto", "synthetic-data-kit", "NeuroX", "dictionary_learning")
wanted = sys.argv[1:] or [*STANDARD, "control_arena"]           # optional arguments: only these task ids
jobs = [load(t, "real_tasks" if t in STANDARD else "real_tasks_new") for t in wanted]
with cf.ThreadPoolExecutor(len(jobs)) as ex:
    for line in ex.map(one, enumerate(jobs)):
        print(line, flush=True)
sys.exit(0)
