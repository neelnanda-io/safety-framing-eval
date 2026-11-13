"""Dry run on the rented machine: build each checkout, run its tests as the sandbox user, and check what the agent could see."""
import json, shutil, sys, time
from sfe.real import RealSandbox, ensure_venv, list_real_tasks, load_real_task, make_checkout, SANDBOX_USER

for tid in (sys.argv[1:] or list_real_tasks()):      # optional arguments: only these repositories
    t = load_real_task(tid); t0 = time.time()
    v = ensure_venv(t)
    ws, repo, base = make_checkout(t, "safety")
    sb = RealSandbox(repo, ws, v, t.get("pythonpath", "."))
    r = sb.baseline_tests(t["test_cmd"])
    print(f"{tid}: tests {r.get('counts')} exit {r['exit']} in {time.time() - t0:.0f}s; left behind {r.get('litter')}")
    if tid == "rsl_rl":
        for c in ["whoami; id -un; pwd; echo $HOME; which python; python -V", "ls -la | head -5", "git status --short | head -3; git log --oneline | head -2",
                  "cat /root/sfe/.env 2>&1 | head -2; ls /root 2>&1 | head -2", "cat ../../../root/sfe/real_tasks/rsl_rl/rubric.json 2>&1 | head -c 120",
                  "python -c \"import urllib.request; print(urllib.request.urlopen('https://example.com', timeout=8).status)\" 2>&1 | tail -1",
                  "python -c \"import torch, os; print(torch.__version__, torch.get_num_threads(), os.cpu_count())\"",
                  "python -m pip download --no-deps -d ../dl six 2>&1 | tail -n 2", "ls /tmp | head -20; ls /root 2>&1 | head -2"]:
            print("  $", c, "\n   ", sb.run_command(c).replace("\n", "\n    ")[:500])
        print("  write_file:", sb.write_file("pkg_new/x.py", "x = 1\n"), "| owner check:", sb.run_command("ls -l pkg_new/x.py; echo y >> pkg_new/x.py && echo appended-ok")[:160].replace("\n", " | "))
        print("  diff lines:", len(sb.diff_against(base).splitlines()), "| list_files head:", sb.list_files().split("\n")[:3])
    shutil.rmtree(ws)
print("sandbox user:", SANDBOX_USER)
