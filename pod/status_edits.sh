#!/bin/bash
# Progress of the description-edit episodes on the rented machine (run there, from /root/sfe).
cd /root/sfe
for f in logs/edits_*.log; do
  [ "$f" = logs/edits_launch.log ] && continue
  total=$(grep " done " "$f" | tail -n 1 | grep -o 'run total=[^ ]*')
  echo "$f: finished $(grep -c ' done ' "$f"), crashed $(grep -c CRASH "$f"), blocked $(grep -c 'blocked by' "$f"), cap hit $(grep -c 'SPEND CAP' "$f") $total"
done
echo "run processes: $(pgrep -fc 'sfe.real --run'); $(uptime | sed 's/.*load/load/'); $(date -u +%H:%M) UTC"
cat logs/edits_launch.log 2>/dev/null | tail -n 2
