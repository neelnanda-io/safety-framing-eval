"""Dry run on a rented machine with a pool of agent users (SFE_SANDBOX_USERS): two checkouts as two users, each repository's
tests, and what one user can see of the other's files. Run as root from /root/sfe with the same environment as pod/edits.sh."""
import shutil
import subprocess
import time

from sfe.real import RealSandbox, agent_can_reach_internet, clean_shared_tmp, ensure_venv, load_real_task, make_checkout

print("agent can reach the internet:", agent_can_reach_internet())
box = {}
for tid, user in (("rsl_rl", "jlee"), ("synthetic-data-kit", "mross")):
    t = load_real_task(tid)
    t0 = time.time()
    ws, repo, base = make_checkout(t, "safety", user)
    sb = RealSandbox(repo, ws, ensure_venv(t), t.get("pythonpath", "."), user)
    r = sb.baseline_tests(t["test_cmd"])
    who = sb.run_command("whoami; echo $USER; umask; echo x > /tmp/scratch_$USER.txt; ls -l /tmp/scratch_$USER.txt | cut -c1-10")
    print(f"{tid} as {user}: tests {r.get('counts')} exit {r['exit']} in {time.time() - t0:.0f}s | " + who.replace("\n", " | ")[:120])
    box[user] = (ws, sb, base)
ws_j, sb_j, base_j = box["jlee"]
ws_m, sb_m, _ = box["mross"]
print("mross listing jlee's checkout:", sb_m.run_command(f"ls {ws_j} 2>&1 | head -2").replace("\n", " | ")[:140])
print("mross reading jlee's scratch file:", sb_m.run_command("cat /tmp/scratch_jlee.txt 2>&1").replace("\n", " | ")[:140])
print("mross sees in /tmp:", sb_m.run_command("ls /tmp | head").replace("\n", " | ")[:200])
print("write_file:", sb_j.write_file("pkg_new/x.py", "x = 1\n"), "| diff lines:", len(sb_j.diff_against(base_j).splitlines()))
for u, (ws, sb, _) in box.items():
    shutil.rmtree(ws)
    print("removed /tmp entries of", u, ":", clean_shared_tmp(user=u))
