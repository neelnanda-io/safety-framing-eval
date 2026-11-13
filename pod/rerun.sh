#!/bin/bash
# Re-run, ONE AT A TIME, the nine episodes spoiled on 11 Nov 2026 by an open internet connection and a shared /tmp
# (reasons: results/real/replaced_episodes.json). Run on the rented machine after pod/setup.sh and pod/offline.sh.
# SFE_CLEAN_SHARED_TMP=1 empties what the agent's user left under /tmp before and after every episode.
cd /root/sfe
export SFE_SANDBOX_USER=akim SFE_SCRUB_USER= SFE_VENV_BASE=/var/tmp/venvs SFE_BASE_PYTHON=$(cat pod/base_python.txt) SFE_CLEAN_SHARED_TMP=1
PY=/opt/harness/bin/python
mkdir -p logs
{
$PY -m sfe.real --run real2_dsflash --models dsflash --tasks NeuroX rsl_rl --seeds 1 2 --concurrency 1 --cap-usd 10 --max-episode-usd 1.5 \
    --only dsflash__NeuroX__safety__s1 dsflash__rsl_rl__capabilities__s1 dsflash__rsl_rl__safety__s2
$PY -m sfe.real --run real2_flash38 --models flash38 --tasks rsl_rl --seeds 1 --concurrency 1 --cap-usd 20 --max-episode-usd 2 \
    --only flash38__rsl_rl__capabilities__s1
$PY -m sfe.real --run real2_opus --models opus --tasks dictionary_learning rsl_rl --seeds 1 --concurrency 1 --cap-usd 95 --max-episode-usd 6 \
    --only opus__dictionary_learning__safety__s1 opus__rsl_rl__capabilities__s1
SFE_FILTER_ATTEMPTS=6 $PY -m sfe.real --run real2_opus --models opus --tasks rsl_rl --framings safety_reworded --seeds 2 --concurrency 1 \
    --cap-usd 95 --max-episode-usd 6 --only opus__rsl_rl__safety_reworded__s2
$PY -m sfe.real --run real2_fable52 --models fable52 --tasks NeuroX dictionary_learning --seeds 1 2 --concurrency 1 --cap-usd 140 --max-episode-usd 9 \
    --only fable52__NeuroX__capabilities__s1 fable52__dictionary_learning__capabilities__s2
echo ALL_RERUNS_DONE
} >> logs/reruns.log 2>&1
