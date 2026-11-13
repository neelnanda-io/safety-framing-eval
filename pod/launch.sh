#!/bin/bash
# Start every remaining real-repository run on the rented machine. Finished episodes (including the stand-ins for the
# ones done on the laptop) are skipped, so this is safe to run again after an interruption.
cd /root/sfe
export SFE_SANDBOX_USER=akim SFE_SCRUB_USER= SFE_VENV_BASE=/var/tmp/venvs SFE_BASE_PYTHON=$(cat pod/base_python.txt)
PY=/opt/harness/bin/python
mkdir -p logs
run() { name=$1; shift; nohup $PY -m sfe.real "$@" >> logs/$name.log 2>&1 & }
A="--seeds 0 1 2"
run carbon   --run real2_carbon   --models carbon   --tasks all $A --concurrency 4 --cap-usd 60  --max-episode-usd 4
run argon    --run real2_argon    --models argon    --tasks all $A --concurrency 4 --cap-usd 55  --max-episode-usd 4
run gem31pro --run real2_gem31pro --models gem31pro --tasks all $A --concurrency 3 --cap-usd 45  --max-episode-usd 4
run flash35  --run real2_flash35  --models flash35  --tasks all $A --concurrency 3 --cap-usd 50  --max-episode-usd 4
run flash38  --run real2_flash38  --models flash38  --tasks all $A --concurrency 3 --cap-usd 20  --max-episode-usd 2
run muse     --run real2_muse     --models muse     --tasks all $A --concurrency 4 --cap-usd 115 --max-episode-usd 7
run grok     --run real2_grok     --models grok     --tasks all $A --concurrency 4 --cap-usd 140 --max-episode-usd 8
run kimi     --run real2_kimi     --models kimi     --tasks all $A --concurrency 3 --cap-usd 60  --max-episode-usd 5
run dsflash  --run real2_dsflash  --models dsflash  --tasks all $A --concurrency 3 --cap-usd 10  --max-episode-usd 1.5
# Claude: the four repositories the provider's filter accepts as written ...
run fable52  --run real2_fable52 --models fable52 --tasks prompto valor NeuroX dictionary_learning $A --concurrency 3 --cap-usd 140 --max-episode-usd 9
run opus     --run real2_opus    --models opus    --tasks prompto valor NeuroX dictionary_learning $A --concurrency 3 --cap-usd 95  --max-episode-usd 6
# ... and the two attack-like repositories with the reworded descriptions (Opus also on the original safety ones, as a control)
export SFE_FILTER_ATTEMPTS=6
run fable52_rsl --run real2_fable52 --models fable52 --tasks rsl_rl --framings safety_reworded capabilities $A --concurrency 2 --cap-usd 140 --max-episode-usd 9
run fable52_sdk --run real2_fable52 --models fable52 --tasks synthetic-data-kit --framings safety_reworded capabilities_reworded $A --concurrency 2 --cap-usd 140 --max-episode-usd 9
run opus_rsl    --run real2_opus --models opus --tasks rsl_rl --framings safety safety_reworded capabilities $A --concurrency 2 --cap-usd 95 --max-episode-usd 6
run opus_sdk    --run real2_opus --models opus --tasks synthetic-data-kit --framings safety safety_reworded capabilities_reworded $A --concurrency 2 --cap-usd 95 --max-episode-usd 6
sleep 3
echo "started $(pgrep -fc 'sfe.real --run') run processes"
