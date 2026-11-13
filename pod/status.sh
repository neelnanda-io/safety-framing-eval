#!/bin/bash
# Progress on the rented machine: finished episodes per run (stand-ins for laptop episodes included) and anything unusual.
cd /root/sfe
echo "$(date -u +%H:%M) UTC; run processes alive: $(pgrep -fc 'sfe.real --run'); load: $(cut -d' ' -f1-3 /proc/loadavg); memory used: $(free -g | awk 'NR==2{print $3"/"$2" GB"}')"
for r in carbon argon gem31pro flash35 flash38 muse grok kimi dsflash fable52 opus; do
  n=$(ls runs/real2_$r/episodes 2>/dev/null | wc -l)
  spent=$(cat logs/${r}*.log 2>/dev/null | grep -o 'run total=\$[0-9.]*' | tail -1)
  crashed=$(cat logs/${r}*.log 2>/dev/null | grep -c 'CRASHED\|turn aborted')
  blocked=$(cat logs/${r}*.log 2>/dev/null | grep -c 'blocked by the provider')
  capped=$(cat logs/${r}*.log 2>/dev/null | grep -c 'SPEND CAP')
  echo "$r: $n saved; $spent; errors $crashed; blocked $blocked; cap hits $capped"
done
