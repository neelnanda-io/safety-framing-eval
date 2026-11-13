#!/bin/bash
# Full episodes for the fine-grained description edits (11 Nov 2026: is it specifically about dual-use or offensive work, and what
# happens when the work is described outright as an attack?).
# Run on a rented machine after pod/setup.sh rsl_rl synthetic-data-kit, the user pool below, and pod/offline.sh.
# Three processes with disjoint pools of agent users, so no two running episodes ever share a user.
cd /root/sfe
export SFE_SANDBOX_USER=akim SFE_SCRUB_USER= SFE_VENV_BASE=/var/tmp/venvs SFE_BASE_PYTHON=$(cat pod/base_python.txt) SFE_CLEAN_SHARED_TMP=1
PY=/opt/harness/bin/python
mkdir -p logs
RSL="fg_none fg_label_only fg_plain_words fg_defender fg_game fg_fraud fg_pentest fg_authorised fg_product_evasion fg_attack fg_neutral_words"
SDK="fg_none fg_label_only fg_plain_words fg_defender fg_phishing fg_jailbreak_data fg_commercial_trigger fg_authorised fg_attack fg_no_backdoor_words"
SFE_SANDBOX_USERS=akim,jlee,mross,tkaur,dwong,spark,rcohen,lnovak,pshah,hyang nohup $PY -m sfe.real --run real3_rsl_rl \
    --models astra sol61s --tasks rsl_rl --framings $RSL --seeds 0 1 --concurrency 10 --cap-usd 130 --max-episode-usd 7 >> logs/edits_rsl_rl.log 2>&1 &
SFE_SANDBOX_USERS=ebauer,fmoreno,agarcia,bnguyen,cdavis,eokafor,gsato,hpatel,iromero,kmuller nohup $PY -m sfe.real --run real3_sdk \
    --models astra sol61s --tasks synthetic-data-kit --framings $SDK --seeds 0 1 --concurrency 10 --cap-usd 130 --max-episode-usd 7 >> logs/edits_sdk.log 2>&1 &
SFE_SANDBOX_USERS=lchen,mjones,nkhan,oreyes nohup $PY -m sfe.real --run real3_sol \
    --models sol --tasks rsl_rl synthetic-data-kit --framings fg_attack fg_none --seeds 0 1 --concurrency 4 --cap-usd 30 --max-episode-usd 4 >> logs/edits_sol.log 2>&1 &
sleep 5
echo "started $(pgrep -fc 'sfe.real --run') run processes"
