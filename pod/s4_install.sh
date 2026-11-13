#!/bin/bash
# S4 (13 Nov 2026): install the generic RL library's environment (autonomous-learning-library, task new_rl) on the rented
# machine. The machine has no name servers while episodes run, so they are restored for the install ONLY, and only when no
# harness process is running (an agent must never have the network). pod/offline.sh removes them again and checks that an
# agent user cannot look up pypi.org. Run as root from /root/sfe:  bash pod/s4_install.sh
set -euo pipefail
cd /root/sfe
n=$(pgrep -fc "sfe\.real --run" || true)
if [ "$n" != "0" ]; then echo "REFUSED: $n harness processes are running; the network must stay off while any agent runs"; exit 1; fi
cp /root/resolv.conf.bak /etc/resolv.conf
echo "name servers restored for the install at $(date -u +%H:%M:%S)"
bash pod/setup.sh autonomous-learning-library || { bash pod/offline.sh; echo "SETUP FAILED (machine taken offline again)"; exit 1; }
bash pod/offline.sh
echo "S4_INSTALL_DONE at $(date -u +%H:%M:%S)"
