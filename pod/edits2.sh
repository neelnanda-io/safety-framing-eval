#!/bin/bash
# Second batch of full episodes for the description edits, started while the first batch (pod/edits.sh) is still running,
# with agent users that the first batch does not use. Added after the first-message probe showed that
#   - dropping only "sleeper-agent-style" changes GPT-6 Astra's first words on the data kit (0 of 10 state a limit), and
#   - GPT-5.6 Sol is the natural contrast for every description, not only the blatant attack.
cd /root/sfe
export SFE_SANDBOX_USER=akim SFE_SCRUB_USER= SFE_VENV_BASE=/var/tmp/venvs SFE_BASE_PYTHON=$(cat pod/base_python.txt) SFE_CLEAN_SHARED_TMP=1
PY=/opt/harness/bin/python
SFE_SANDBOX_USERS=lchen,mjones,nkhan,oreyes nohup $PY -m sfe.real --run real3_sdk_b \
    --models astra sol61s --tasks synthetic-data-kit --framings fg_no_sleeper --seeds 0 1 --concurrency 4 --cap-usd 30 --max-episode-usd 7 >> logs/edits_sdk_b.log 2>&1 &
SFE_SANDBOX_USERS=pwright,qzhou,rsingh,sadams nohup $PY -m sfe.real --run real3_sol_rsl --models sol --tasks rsl_rl \
    --framings fg_label_only fg_plain_words fg_defender fg_game fg_fraud fg_pentest fg_authorised fg_product_evasion fg_neutral_words safety capabilities \
    --seeds 0 --concurrency 4 --cap-usd 60 --max-episode-usd 4 >> logs/edits_sol_rsl.log 2>&1 &
SFE_SANDBOX_USERS=tbaker,uortiz,vkim,wevans nohup $PY -m sfe.real --run real3_sol_sdk --models sol --tasks synthetic-data-kit \
    --framings fg_label_only fg_plain_words fg_defender fg_phishing fg_jailbreak_data fg_commercial_trigger fg_authorised fg_no_backdoor_words fg_no_sleeper safety capabilities \
    --seeds 0 --concurrency 4 --cap-usd 60 --max-episode-usd 4 >> logs/edits_sol_sdk.log 2>&1 &
sleep 5
echo "$(date -u +%H:%M) second batch started: $(pgrep -fc 'sfe.real --run') run processes" >> logs/edits_launch.log
