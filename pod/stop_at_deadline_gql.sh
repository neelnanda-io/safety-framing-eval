#!/bin/sh
# The safety net of pod/stop_at_deadline.sh, with the machine stopped through RunPod's GraphQL API (pod/rp_gql.py)
# instead of `runpodctl pod stop`. Added 21 Nov 2026: runpodctl 2.1.9 on the laptop calls rest.runpod.io, which does not
# resolve here ("no such host"), so the original script would log "machine stopped" while the machine kept running.
# Everything else is as in pod/stop_at_deadline.sh: every five minutes copy results back; once the deadline has passed AND
# the machine has had no run process for two checks in a row: final copy, confirm every finished episode is here, remove
# the API key there and STOP the machine (stop, never delete). Optional HARD deadline: stop then even if runs are going
# (after a final copy and check). If the machine cannot be reached for 30 minutes past the deadline, stop it anyway.
# The stop is retried up to three times and the reply checked for desiredStatus EXITED; the outcome is logged either way.
#
# Usage: SFE_POD_HOST=<host file> pod/stop_at_deadline_gql.sh <deadline as epoch seconds> [hard deadline as epoch seconds]
# Log: ${SFE_STOPPER_LOG:-runs_watchdog.log}
cd "$(dirname "$0")/.." || exit 1
read -r POD IP PORT < "${SFE_POD_HOST:-pod/host.txt}"     # the rented machine: id, address, ssh port
LOG=${SFE_STOPPER_LOG:-runs_watchdog.log}
DEADLINE=${1:?usage: stop_at_deadline_gql.sh <deadline as epoch seconds> [hard deadline]}
HARD=${2:-0}
idle=0
unreachable=0
stop_pod() {          # STOP (never delete) through the GraphQL API; prints STOPPED or FAILED plus the reply
  for t in 1 2 3; do
    reply=$(python3 pod/rp_gql.py "mutation { podStop(input: {podId: \"$POD\"}) { id desiredStatus } }" 2>&1)
    case "$reply" in *'"desiredStatus":"EXITED"'*) echo "STOPPED $reply"; return 0;; esac
    /bin/sleep 20
  done
  echo "FAILED $reply"
  return 1
}
echo "$(date) deadline safety net (GraphQL stop) started, pid $$: machine $POD will be stopped once quiet after $(date -r "$DEADLINE")$( [ "$HARD" -gt 0 ] && echo ", and in any case at $(date -r "$HARD")")" >> $LOG
while true; do
  n=$(pod/ssh.sh 'pgrep -fc "^/opt/harness/bin/python -m sfe.real --run"' 2>/dev/null)
  pod/pull.sh >/dev/null 2>&1
  if [ "$n" = "0" ]; then idle=$((idle + 1)); else idle=0; fi
  if [ -z "$n" ]; then unreachable=$((unreachable + 1)); else unreachable=0; fi
  now=$(date +%s)
  if [ "$now" -ge "$DEADLINE" ] && [ "$idle" -ge 2 ]; then
    ok=0
    for try in 1 2 3; do
      pod/pull.sh >/dev/null 2>&1
      here=$(python3 pod/verify_copy.py 2>&1 | tail -n 1)      # "COPY_OK <n>" when every episode file there has an identical copy here
      case "$here" in COPY_OK*) ok=1; break;; esac
      /bin/sleep 30
    done
    if [ "$ok" = "1" ]; then
      pod/ssh.sh 'rm -f /root/sfe/.env' 2>/dev/null
      res=$(stop_pod)
      echo "$(date) deadline passed and no runs: every episode file copied to runs_pod/ ($here), key removed, stop: $res" >> $LOG
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
    res=$(stop_pod)
    echo "$(date) HARD deadline reached: runs may still have been going; last copy check: $here; key removed; stop: $res" >> $LOG
    exit 0
  fi
  if [ "$now" -ge $((DEADLINE + 1800)) ] && [ "$unreachable" -ge 6 ]; then
    res=$(stop_pod)
    echo "$(date) machine $POD unreachable for 30 minutes past the deadline: stop without a final copy: $res" >> $LOG
    exit 0
  fi
  /bin/sleep 300
done
