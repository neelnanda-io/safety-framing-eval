#!/bin/sh
# Copy finished episodes and logs from the rented machine (pod/host.txt) into runs_pod/ (a staging copy), then merge the new ones into runs/.
cd "$(dirname "$0")/.." || exit 1
read -r POD IP PORT < "${SFE_POD_HOST:-pod/host.txt}"
RS="ssh -i ${SFE_POD_SSH_KEY:-$HOME/.ssh/id_ed25519} -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR -o ConnectTimeout=20 -p $PORT"
mkdir -p runs_pod/runs runs_pod/logs
rsync -az -e "$RS" root@"$IP":/root/sfe/runs/ runs_pod/runs/ || exit 2
rsync -az -e "$RS" root@"$IP":/root/sfe/logs/ runs_pod/logs/ || exit 2
python3 pod/merge.py
