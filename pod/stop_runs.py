"""Stop every harness process whose run name starts with a given prefix, with its whole process group (its agents' test
runs included). Matches only processes whose program is the harness's Python, so it never matches the shell running it.
Run on the machine as root:  /opt/harness/bin/python pod/stop_runs.py new_generic4_"""
import os
import signal
import sys
from pathlib import Path

prefix = sys.argv[1]
stopped = []
for d in Path("/proc").iterdir():
    if not d.name.isdigit():
        continue
    try:
        args = (d / "cmdline").read_bytes().split(b"\0")
    except OSError:
        continue
    args = [a.decode(errors="replace") for a in args if a]
    if len(args) > 4 and args[0] == "/opt/harness/bin/python" and args[1:3] == ["-m", "sfe.real"] and "--run" in args:
        run = args[args.index("--run") + 1]
        if run.startswith(prefix):
            pid = int(d.name)
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
            stopped.append((run, pid, pgid))
for s in stopped:
    print("stopped", *s)
print(f"{len(stopped)} harness processes stopped")
