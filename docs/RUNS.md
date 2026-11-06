# Runs in the data bundle

Every folder under `runs/` in `episodes.tar.gz`. "Primary" runs are the ones the headline numbers use. All runs use
3 turns x 15 tool calls, an 8,000-character command-output cap and the default system prompt unless stated.

## Contents

- [Original six tasks](#original-six-tasks)
- [Harder tasks](#harder-tasks)
- [Replays and native episodes](#replays-and-native-episodes)
- [Spoiled, pilot and calibration runs](#spoiled-pilot-and-calibration-runs)

---

## Original six tasks

| run | model (config key) | framings | seeds | status |
|---|---|---|---|---|
| `main3_astra` | GPT-6 Astra (`astra`) | safety, capabilities | 0–5 | primary |
| `main3_astra_careful` | GPT-6 Astra, "be careful" system prompt | safety, capabilities | 0–2 | primary |
| `main3_sol` | GPT-5.6 Sol (`sol`) | safety, capabilities | 0–5 | primary |
| `w2_sol61` | GPT-6.1 Sol (`sol61`) | safety, capabilities | 0–5 | primary |
| `w3_sol61_rep` | GPT-6.1 Sol | safety, capabilities | 6–11 | primary (replication) |
| `w3_sol61_neutral` | GPT-6.1 Sol | neutral | 0–5 | primary (third arm) |
| `w2_fable` | Claude Fable 5.1 (`fable`) | safety, capabilities | 0–5 | primary |
| `w2_opus` | Claude Opus 5.5 (`opus`) | safety, capabilities | 0–5 | primary |
| `w2_argon` | Gemini 4 Argon (`argon`) | safety, capabilities | 0–5 | primary |
| `w2_flash38` | Gemini 3.8 Flash (`flash38`) | safety, capabilities | 0–5 | primary |
| `w4_flash38_more` | Gemini 3.8 Flash; sabotage monitor and model-organism tasks only | safety, capabilities | 6–17 | primary |
| `w2_kimi` | Kimi K3 (`kimi`) | safety, capabilities | 0–5 | primary |
| `w4_kimi_more` | Kimi K3; deception probe and red-teaming loop only | safety, capabilities | 6–17 | primary |
| `w2_dsflash` | DeepSeek V4.1 Flash (`dsflash`) | safety, capabilities | 0–5 | primary |
| `w3_terra61` | GPT-6.1 Terra (`terra61`) | safety, capabilities | 0–5 | primary |
| `w4_terra61_more` | GPT-6.1 Terra; sabotage monitor and model-organism tasks only | safety, capabilities | 6–17 | primary |
| `w3_sol6` | GPT-6 Sol (`sol6`) | safety, capabilities | 0–5 | primary |
| `w3_luna6` | GPT-6 Luna (`luna6`) | safety, capabilities | 0–5 | primary |

## Harder tasks

Four tasks: `monitor_evasion_rl`, `jailbreak_corpus`, `control_eval`, `sae_audit`. "scarce" = command output capped at
2,000 characters (`SFE_MAX_OUTPUT_CHARS=2000`).

| run | model | condition | seeds | status |
|---|---|---|---|---|
| `hard_std_sol` | GPT-5.6 Sol | standard | 0–5 | primary |
| `hard_scarce_sol` | GPT-5.6 Sol | scarce | 0–5 | primary |
| `hard_std_sol61s` | GPT-6.1 Sol, OpenAI standard tier (`sol61s`) | standard | 0–5 | primary |
| `hard_scarce_sol61s` | GPT-6.1 Sol, OpenAI standard tier | scarce | 0–5 | primary |
| `hard_std_astra` | GPT-6 Astra via OpenAI's own API (`astra_oai`) | standard | 0–5 | primary |
| `hard_scarce_astra` | GPT-6 Astra via OpenAI's own API | scarce | 0–5 | primary |
| `hard_std_terra61` | GPT-6.1 Terra | standard | 0–5 | primary |
| `hard_scarce_terra61` | GPT-6.1 Terra | scarce | 0–5 | primary |
| `hard_std_kimi` | Kimi K3 | standard | 0–5 | primary |
| `hard_scarce_kimi` | Kimi K3 | scarce | 0–5 | primary |
| `hard_std_flash38` | Gemini 3.8 Flash | standard | 0–5 | primary |
| `hard_scarce_flash38` | Gemini 3.8 Flash | scarce | 0–5 | floor: 0% on every episode, not used |

## Replays and native episodes

| run | what |
|---|---|
| `native_astra` | GPT-6 Astra through OpenAI's Responses API with reasoning carried across calls (as in Codex) and a reasoning summary recorded per call; gap tasks only; some episodes incomplete because the OpenAI account ran out of credit |
| `native_sol61` | the same for GPT-6.1 Sol |

Interrogation, decision-point and why-probe outputs are in `results/interrogation/`, `results/decisions/` and
`results/why_probe.json` in the repository itself.

## Spoiled, pilot and calibration runs

| run | what |
|---|---|
| `v1_main_astra` | full run spoiled by command filter v1 (blocked `open(`, `...`, `~`), symmetric across framings; partial |
| `v1_main_sol` | same, GPT-5.6 Sol |
| `v1_main_astra_careful` | same, "be careful" prompt |
| `main2_astra` | full run spoiled by command filter v2 (blocked `/`, `/dev/null`, `/tmp`), symmetric across framings |
| `main2_sol` | same, GPT-5.6 Sol |
| `main2_astra_careful` | same, "be careful" prompt |
| `pilot_astra` | first pilot: old 14-item rubric, repository pasted into turn 1, 20 calls per turn (ceiling) |
| `pilot2_astra` | second pilot on three hardened tasks |
| `calib_hard` | hard-task calibration, neutral framing, GPT-5.6 Sol, standard |
| `calib_hard_std` | same, two tasks, two seeds |
| `calib_hard_b6` | 6 calls per turn |
| `calib_hard_b8` | 8 calls per turn |
| `calib_A` | 3 turns x 8 calls |
| `calib_B` | 2 turns x 15 calls |
| `calib_C` | 3,000-character output cap |
| `calib_D` | 3,000-character cap and 3 turns x 8 calls |
| `calib_E` | 2,000-character cap (chosen as "scarce") |
| `smoke7` | one-turn smoke test of seven models, 8 calls |
| `smoke7b` | same at 15 calls |
