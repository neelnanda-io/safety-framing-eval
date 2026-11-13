#!/bin/bash
# Fourth batch (11 Nov 2026, 19:00 GMT): is the limit only ANNOUNCED when the user's message names the purpose?
#   - more seeds of the two descriptions that imply the attack-like purpose without naming it, and
#   - the original descriptions placed only in the README section (the user's message is the bare request).
# Agent users here are free: the batches that used them have finished.
cd /root/sfe
export SFE_SANDBOX_USER=akim SFE_SCRUB_USER= SFE_VENV_BASE=/var/tmp/venvs SFE_BASE_PYTHON=$(cat pod/base_python.txt) SFE_CLEAN_SHARED_TMP=1
PY=/opt/harness/bin/python
SFE_SANDBOX_USERS=ebauer,fmoreno,agarcia,bnguyen,cdavis,eokafor nohup $PY -m sfe.real --run real3_implied --models astra sol61s --tasks synthetic-data-kit \
    --framings fg_plain_words --seeds 2 3 4 5 --concurrency 6 --cap-usd 40 --max-episode-usd 7 >> logs/edits_implied.log 2>&1 &
SFE_SANDBOX_USERS=gsato,hpatel,iromero,kmuller,lchen,mjones,nkhan,oreyes nohup $PY -m sfe.real --run real3_readme --models astra sol61s --tasks synthetic-data-kit \
    --framings fg_readme_only fg_readme_only_product --seeds 0 1 --concurrency 8 --cap-usd 40 --max-episode-usd 7 >> logs/edits_readme_sdk.log 2>&1 &
# the RL library's test suite is the heavy one: wait for the first batch's RL episodes to finish before adding more of them
while pgrep -f "sfe.real --run real3_rsl_rl " > /dev/null; do sleep 20; done
SFE_SANDBOX_USERS=tbaker,uortiz,vkim,wevans,dfox,egray,fhunt,gcole nohup $PY -m sfe.real --run real3_readme_rsl --models astra sol61s --tasks rsl_rl \
    --framings fg_readme_only fg_readme_only_product --seeds 0 1 2 3 --concurrency 8 --cap-usd 60 --max-episode-usd 7 >> logs/edits_readme_rsl.log 2>&1 &
sleep 5
echo "$(date -u +%H:%M) fourth batch started: $(pgrep -fc 'sfe.real --run') run processes" >> logs/edits_launch.log
