#!/bin/sh
# Safety net that needs no Claude session: copy results back every five minutes; once the rented machine has had no run
# process for two checks in a row, do a final copy, confirm every finished episode is here, remove the API key there and
# STOP the machine (stop, not delete). Log: runs_watchdog.log
cd "$(dirname "$0")/.." || exit 1
POD=${SFE_POD_ID:?set SFE_POD_ID to the rented machine id}
LOG=runs_watchdog.log
idle=0
while true; do
  n=$(pod/ssh.sh 'pgrep -fc "sfe.real --run"' 2>/dev/null)
  pod/pull.sh >/dev/null 2>&1
  if [ "$n" = "0" ]; then idle=$((idle + 1)); else idle=0; fi
  if [ "$idle" -ge 2 ]; then
    ok=0
    for try in 1 2 3; do
      pod/pull.sh >/dev/null 2>&1
      remote=$(pod/ssh.sh 'cd /root/sfe && grep -L "\"stub\": true" runs/*/episodes/*.json 2>/dev/null | wc -l' 2>/dev/null | tr -d ' ')
      here=$(grep -L '"stub": true' runs_pod/runs/*/episodes/*.json 2>/dev/null | wc -l | tr -d ' ')
      if [ -n "$remote" ] && [ "$remote" = "$here" ]; then ok=1; break; fi
      /bin/sleep 30
    done
    if [ "$ok" = "1" ]; then
      pod/ssh.sh 'rm -f /root/sfe/.env' 2>/dev/null
      runpodctl pod stop $POD >/dev/null 2>&1
      echo "$(date) all runs finished: $here cloud episodes copied to runs_pod/, key removed, machine $POD stopped" >> $LOG
    else
      echo "$(date) runs finished but the copy could not be confirmed (machine has $remote, here $here): machine LEFT RUNNING" >> $LOG
    fi
    exit 0
  fi
  /bin/sleep 300
done
