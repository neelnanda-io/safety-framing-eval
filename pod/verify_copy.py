"""Check that every finished episode file on the rented machine (pod/host.txt) has an identical copy in runs_pod/.
Exit code 0 and "COPY_OK <n>" if so; otherwise exit 1 and list what differs. Used before the machine is stopped."""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
r = subprocess.run([str(ROOT / "pod" / "ssh.sh"), "cd /root/sfe && md5sum runs/*/episodes/*.json 2>/dev/null"],
                   capture_output=True, text=True, timeout=120)
if r.returncode not in (0, 1):
    print("could not reach the machine:", r.stderr[:200])
    sys.exit(1)
bad, n = [], 0
for line in r.stdout.splitlines():
    digest, path = line.split(None, 1)
    local = ROOT / "runs_pod" / path.strip()
    n += 1
    if not local.exists() or hashlib.md5(local.read_bytes()).hexdigest() != digest:
        bad.append(path.strip())
if bad:
    print(f"NOT COPIED or different: {len(bad)} of {n}: {bad[:10]}")
    sys.exit(1)
print(f"COPY_OK {n}")
