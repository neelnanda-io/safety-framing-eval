#!/bin/sh
# Safety net with a deadline, needing no Claude session. Use while the rented machine is deliberately kept on for
# further runs (finish_when_done.sh stops it the first time it goes quiet, which is wrong between two batches).
#
# Every five minutes: copy results back. Once the deadline has passed AND the machine has had no run process for two
# checks in a row: final copy, confirm every finished episode is here, remove the API key there and STOP the machine
# (stop, not delete). If the machine cannot be reached at all for 30 minutes past the deadline, stop it anyway: nothing
# more can be copied from a machine that does not answer, and it would otherwise bill indefinitely.
#
# Optional second argument (added 13 Nov 2026): a HARD deadline. At that time the machine is stopped even if runs are
# still going (after a final copy and check), so a hung run cannot spend past the RunPod budget.
#
# Usage: pod/stop_at_deadline.sh <deadline as epoch seconds> [hard deadline as epoch seconds]      Log: runs_watchdog.log
cd "$(dirname "$0")/.." || exit 1
read -r POD IP PORT < "${SFE_POD_HOST:-pod/host.txt}"     # the rented machine: id, address, ssh port
LOG=runs_watchdog.log
DEADLINE=${1:?usage: stop_at_deadline.sh <deadline as epoch seconds> [hard deadline]}
HARD=${2:-0}
idle=0
unreachable=0
echo "$(date) deadline safety net started: machine $POD will be stopped once quiet after $(date -r "$DEADLINE")$( [ "$HARD" -gt 0 ] && echo ", and in any case at $(date -r "$HARD")")" >> $LOG
while true; do
  n=$(pod/ssh.sh 'pgrep -fc "sfe.real --run"' 2>/dev/null)
  pod/pull.sh >/dev/null 2>&1
  if [ "$n" = "0" ]; then idle=$((idle + 1)); else idle=0; fi
  if [ -z "$n" ]; then unreachable=$((unreachable + 1)); else unreachable=0; fi
  now=$(date +%s)
  if [ "$now" -ge "$DEADLINE" ] && [ "$idle" -ge 2 ]; then
    ok=0
    for try in 1 2 3; do
      pod/pull.sh >/dev/null 2>&1
      here=$(python3 pod/verify_copy.py 2>&1 | tail -n 1)      # "COPY_OK <n>" when every episode file there has an identical copy here
      remote="$here"
      case "$here" in COPY_OK*) ok=1; break;; esac
      /bin/sleep 30
    done
    if [ "$ok" = "1" ]; then
      pod/ssh.sh 'rm -f /root/sfe/.env' 2>/dev/null
      runpodctl pod stop $POD >/dev/null 2>&1
      echo "$(date) deadline passed and no runs: every episode file copied to runs_pod/ ($here), key removed, machine $POD stopped" >> $LOG
    else
      echo "$(date) deadline passed but the copy could not be confirmed ($here): machine LEFT RUNNING" >> $LOG
    fi
    exit 0
  fi
  if [ "$HARD" -gt 0 ] && [ "$now" -ge "$HARD" ]; then
    for try in 1 2 3; do
      pod/pull.sh >/dev/null 2>&1
      here=$(python3 pod/verify_copy.py 2>&1 | tail -n 1)
      case "$here" in COPY_OK*) break;; esac
      /bin/sleep 30
    done
    pod/ssh.sh 'rm -f /root/sfe/.env' 2>/dev/null
    runpodctl pod stop $POD >/dev/null 2>&1
    echo "$(date) HARD deadline reached: runs may still have been going; last copy check: $here; key removed, machine $POD stopped" >> $LOG
    exit 0
  fi
  if [ "$now" -ge $((DEADLINE + 1800)) ] && [ "$unreachable" -ge 6 ]; then
    runpodctl pod stop $POD >/dev/null 2>&1
    echo "$(date) machine $POD unreachable for 30 minutes past the deadline: stopped it without a final copy (copies ran every 5 minutes until it stopped answering)" >> $LOG
    exit 0
  fi
  /bin/sleep 300
done
