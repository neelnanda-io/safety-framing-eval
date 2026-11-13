#!/bin/bash
# Third batch: the five descriptions added after the first probe, which separate "offensive", "evades a detector" and
# "hidden" from "gets prohibited behaviour past a safeguard". Agent users here are not used by the other batches.
cd /root/sfe
export SFE_SANDBOX_USER=akim SFE_SCRUB_USER= SFE_VENV_BASE=/var/tmp/venvs SFE_BASE_PYTHON=$(cat pod/base_python.txt) SFE_CLEAN_SHARED_TMP=1
PY=/opt/harness/bin/python
SFE_SANDBOX_USERS=xliu,ymorris,zhall,abell,bcruz,cdiaz nohup $PY -m sfe.real --run real3_more --models astra sol61s --tasks rsl_rl \
    --framings fg_pentest_plain fg_jailbreaker fg_privacy fg_hidden_no_monitor --seeds 0 1 --concurrency 6 --cap-usd 50 --max-episode-usd 7 >> logs/edits_more.log 2>&1 &
SFE_SANDBOX_USERS=dfox,egray,fhunt,gcole nohup $PY -m sfe.real --run real3_more_sdk --models astra sol61s --tasks synthetic-data-kit \
    --framings fg_password_locked --seeds 0 1 --concurrency 4 --cap-usd 30 --max-episode-usd 7 >> logs/edits_more_sdk.log 2>&1 &
sleep 5
echo "$(date -u +%H:%M) third batch started: $(pgrep -fc 'sfe.real --run') run processes" >> logs/edits_launch.log
