#!/bin/bash
# Sixth batch (11 Nov 2026, about 20:00 GMT). Run only when NO other episode is running on the machine.
#  (a) Repair: the two episodes spoiled when one agent user was given to two running episodes at 19:06.
#  (b) Claude Fable 5.2 follow-up: more seeds on the two measurement repositories where it completed fewer checklist items
#      under the safety description (dictionary_learning 10.2% against 16.9%, NeuroX 11.1% against 14.0%, three episodes each).
cd /root/sfe
export SFE_SANDBOX_USER=akim SFE_SCRUB_USER= SFE_VENV_BASE=/var/tmp/venvs SFE_BASE_PYTHON=$(cat pod/base_python.txt) SFE_CLEAN_SHARED_TMP=1
PY=/opt/harness/bin/python
rm -f runs/real3_implied_rsl/episodes/astra__rsl_rl__fg_hidden_no_monitor__s2.json runs/real3_rsl_rl/episodes/sol61s__rsl_rl__fg_neutral_words__s1.json
SFE_SANDBOX_USERS=akim,jlee nohup $PY -m sfe.real --run real3_rsl_rl --models sol61s --tasks rsl_rl --framings fg_neutral_words --seeds 1 \
    --concurrency 1 --cap-usd 150 --max-episode-usd 7 --only sol61s__rsl_rl__fg_neutral_words__s1 >> logs/edits_repair.log 2>&1 &
SFE_SANDBOX_USERS=mross,tkaur nohup $PY -m sfe.real --run real3_implied_rsl --models astra --tasks rsl_rl --framings fg_hidden_no_monitor --seeds 2 \
    --concurrency 1 --cap-usd 150 --max-episode-usd 7 --only astra__rsl_rl__fg_hidden_no_monitor__s2 >> logs/edits_repair.log 2>&1 &
SFE_SANDBOX_USERS=dwong,spark,rcohen,lnovak,pshah,hyang,ebauer,fmoreno nohup $PY -m sfe.real --run real2_fable52_more --models fable52 \
    --tasks NeuroX dictionary_learning --seeds 3 4 5 6 --concurrency 8 --cap-usd 80 --max-episode-usd 9 >> logs/edits_fable_more.log 2>&1 &
sleep 5
echo "$(date -u +%H:%M) sixth batch started: $(pgrep -fc 'sfe.real --run') run processes" >> logs/edits_launch.log
