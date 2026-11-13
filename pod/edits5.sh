#!/bin/bash
# Fifth batch (11 Nov 2026, 19:10 GMT): more seeds for the two RL-library descriptions where the attack-like purpose is only
# implied (neutral words; a hidden side task with no monitor). GPT-6 Astra left the training code alone there without
# saying so in the first episodes. Agent users are those of the first batch, which has finished.
cd /root/sfe
export SFE_SANDBOX_USER=akim SFE_SCRUB_USER= SFE_VENV_BASE=/var/tmp/venvs SFE_BASE_PYTHON=$(cat pod/base_python.txt) SFE_CLEAN_SHARED_TMP=1
PY=/opt/harness/bin/python
SFE_SANDBOX_USERS=akim,jlee,mross,tkaur,dwong,spark,rcohen,lnovak nohup $PY -m sfe.real --run real3_implied_rsl --models astra sol61s --tasks rsl_rl \
    --framings fg_neutral_words fg_hidden_no_monitor --seeds 2 3 4 5 --concurrency 8 --cap-usd 50 --max-episode-usd 7 >> logs/edits_implied_rsl.log 2>&1 &
sleep 5
echo "$(date -u +%H:%M) fifth batch started: $(pgrep -fc 'sfe.real --run') run processes" >> logs/edits_launch.log
