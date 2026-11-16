# Runs in the data release

Every folder in the `data-v3` release, by archive. Each archive unpacks at the repository root into
`runs/<run>/episodes/*.json` (plus `replaced/` and `superseded/` where noted) or `results/real/<folder>/*.json`.
`MANIFEST.md` in the release gives the number of files and the size of every run. "Primary" runs are the ones the
headline numbers use. Toy-task runs use 3 turns x 15 tool calls, an 8,000-character command-output cap and the default
system prompt unless stated; real-repository runs use 3 turns x 25 tool calls and the two closing questions.

`data-v1` (6 Nov 2026) held the toy-task runs only; `data-v2` (13 Nov 2026) held everything run until then; `data-v3` (16
Nov 2026) holds the four archives of `data-v2` unchanged (same checksums) and adds `v3-additions.tar.gz` with the runs of 16
Nov, and supersedes both. The earlier releases stay available, but `data-v3` is the version to use.

## Contents

- [Archives](#archives)
- [Toy tasks: original six](#toy-tasks-original-six)
- [Toy tasks: harder four](#toy-tasks-harder-four)
- [Toy tasks: replays, description family, pilots and calibration](#toy-tasks-replays-description-family-pilots-and-calibration)
- [Real repositories (10-11 Nov 2026)](#real-repositories-10-11-nov-2026)
- [Description edits (11 Nov 2026 onwards)](#description-edits-11-nov-2026-onwards)
- [New repositories (13 Nov 2026 onwards)](#new-repositories-13-nov-2026-onwards)
- [Not in the release](#not-in-the-release)

---

## Archives

| archive | what |
|---|---|
| `toy-tasks.tar.gz` | the ten toy tasks, every model; the description family; replays with reasoning carried; pilots and calibration |
| `real-repos.tar.gz` | six real open-source repositories under a safety and a product description, fourteen models |
| `description-edits.tar.gz` | single-change rewrites of the two attack-like descriptions: full episodes and the first-reply probes |
| `new-repos.tar.gz` | eighteen further repositories and ten stated uses of one generic library: full episodes and first replies |
| `v3-additions.tar.gz` | the runs of 16 Nov 2026 (nine harmless-use episodes of the two Claude models, the eleven new descriptions: below), and the full licence texts of the third-party repositories in `LICENSES/` (the copies in the other four archives are placeholders) |

```bash
gh release download data-v3 --repo neelnanda-io/safety-framing-eval      # all five archives (or -p <name>)
for f in *.tar.gz; do tar xzf "$f"; done
```

What was changed on the way out (`scripts/pack_data.py`): absolute paths into the original machine's home folder are
`<repo>`, `<venv>` or `<home>`; the local username is `<user>`; e-mail addresses (including repository maintainers' addresses
in `git log` output) are `<email>`, except the harness's made-up identity `akim@users.noreply.github.com` and example
domains. Episodes on the five repositories with no licence keep the agent's messages, reasoning summaries, tool names and
arguments, test counts and per-file diff statistics, but the text of tool results, test output, diffs and written files is
replaced by a placeholder (`THIRD_PARTY_NOTICES.md` in each archive lists every repository, its licence and pinned commit;
`LICENSES/` holds the licence texts). Encrypted reasoning blobs (`reasoning.encrypted`, which only the provider can read)
are kept as returned.

## Toy tasks: original six

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

## Toy tasks: harder four

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

## Toy tasks: replays, description family, pilots and calibration

| run | what |
|---|---|
| `native_astra` | GPT-6 Astra through OpenAI's Responses API with reasoning carried across calls (as in Codex) and a reasoning summary recorded per call; gap tasks only; some episodes incomplete because the OpenAI account ran out of credit |
| `native_sol61` | the same for GPT-6.1 Sol |
| `fam_me_astra`, `fam_me_sol61s`, `fam_me_sol` | GPT-6 Astra, GPT-6.1 Sol (standard tier), GPT-5.6 Sol: monitor-evasion task under six descriptions (`capabilities`, `safety_label_only`, `safety_benign`, `product_evasion`, `safety`, `safety_defensive`; GPT-5.6 Sol has no `safety_label_only`), seeds 0–5, with the closing questions (`--debrief`) |
| `fam_dm_astra`, `fam_dm_sol61s`, `fam_dm_sol` | same three: sabotage-monitor task under four descriptions (`capabilities`, `safety_benign`, `product_sabotage`, `safety`), seeds 0–5 |
| `fam_me_notell_astra`, `fam_me_notell_sol61s` | monitor-evasion task, safety and capabilities, after removing the "planted items" line from its test file |
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

Interrogation, decision-point and why-probe outputs are in `results/interrogation/`, `results/decisions/` and
`results/why_probe.json` in the repository itself; answers to the closing questions for older runs are in `results/debrief/`.

## Real repositories (10-11 Nov 2026)

Six repositories (`rsl_rl`, `synthetic-data-kit`, `valor`, `prompto`, `NeuroX`, `dictionary_learning`) x two descriptions
(`safety`, `capabilities`) x seeds 0–2 unless stated. Checklist grades are in `results/real/grades/<judge>/` in the
repository. Each episode file records `platform` (the laptop or a rented Linux machine), `sandbox_user` and, for re-runs,
`isolation`.

| run | model (config key) | notes |
|---|---|---|
| `real_astra` (seeds 0–2 and one seed-3 episode), `real_astra_b` (seed 3 and part of seed 4) | GPT-6 Astra (`astra`) | 57 episodes |
| `real_sol61s` (seeds 0–2 and one seed-3 episode), `real_sol61s_b` (seeds 3–5, 29 of 36) | GPT-6.1 Sol, standard tier (`sol61s`) | 66 episodes |
| `real_sol` | GPT-5.6 Sol (`sol`) | 36 episodes |
| `real_pilot` | all three | one synthetic-data-kit safety episode each, to measure cost |
| `real2_carbon` | Gemini 4 Carbon (`carbon`) | `synthetic-data-kit` safety blocked by Google's filter, 3 of 3 |
| `real2_argon` | Gemini 4 Argon (`argon`) | same |
| `real2_gem31pro` | Gemini 3.1 Pro (`gem31pro`) | |
| `real2_flash35` | Gemini 3.5 Flash (`flash35`) | |
| `real2_flash38` | Gemini 3.8 Flash (`flash38`) | 1 episode replaced |
| `real2_muse` | Muse Wonder (`muse`) | endpoint accepts only `tool_choice: auto` |
| `real2_grok` | Grok 4.7 (`grok`) | |
| `real2_kimi` | Kimi K3 (`kimi`) | |
| `real2_dsflash` | DeepSeek V4.1 Flash (`dsflash`) | 3 episodes replaced |
| `real2_fable52` | Claude Fable 5.2 (`fable52`) | framings `safety_reworded` on `rsl_rl` and `synthetic-data-kit`, `capabilities_reworded` on `synthetic-data-kit` (originals blocked by Anthropic's filter); 2 episodes replaced |
| `real2_fable52_more` | Claude Fable 5.2 | `NeuroX` and `dictionary_learning`, both descriptions, seeds 3–6: a check of a first-seed gap that mostly did not hold |
| `real2_opus` | Claude Opus 5.5 (`opus`) | same reworded framings, plus the original safety framings as a control; 3 episodes replaced |

| `real2_musespark` | Muse Spark Open (`musespark`) | added 13 Nov; host: Modal |
| `real2_dsv4pro` | DeepSeek V4 Pro (`dsv4pro`) | added 13 Nov |
| `real2_dsv4flash` | DeepSeek V4 Flash (`dsv4flash`) | added 13 Nov |
| `real2_qwen36` | Qwen3.6 27B (`qwen36`) | added 13 Nov |
| `real2_qwen38` | Qwen3.8 27B (`qwen38`) | added 13 Nov |
| `real2_luna6` | GPT-6 Luna (`luna6`) | added 13 Nov |
| `real2_terra61` | GPT-6.1 Terra (`terra61`) | added 13 Nov |
| `real2_hydrogen` | Gemini 4 Hydrogen (`hydrogen`) | added 13 Nov; `synthetic-data-kit` safety blocked by Google's filter, 3 of 3 |

The eight runs added on 13 Nov ran on a rented Linux machine with no name servers and one Unix user per episode
(`pod/launch_covert.py`); `results/real/panel22.json` and `panel22_analysis.txt` hold the twenty-two-model analysis.

`runs/<run>/replaced/` holds episodes spoiled by an open internet connection or a shared `/tmp` folder;
`results/real/replaced_episodes.json` says why, and the file of the same name under `runs/<run>/episodes/` is the clean
re-run (one at a time, no internet, `/tmp` emptied between episodes; `pod/rerun.sh`). `runs/<run>/superseded/` holds
episodes recorded before provider-filter refusals were handled (the harness then carried on after a refused turn).

## Description edits (11 Nov 2026 onwards)

The two attack-like repositories under single-change rewrites of their safety description (`fg_*` framings in
`real_tasks/rsl_rl/task.json` and `real_tasks/synthetic-data-kit/task.json`; each has an `edit` field saying what changed).
Full episodes ran on a rented machine with no internet and one Unix user per episode.

| run or folder | model | descriptions | seeds |
|---|---|---|---|
| `results/real/first_words` | GPT-6 Astra, GPT-6.1 Sol | the model's first message only, 10 samples per description and model (`python -m sfe.first_words`) | k0–k9 |
| `real3_rsl_rl` | GPT-6 Astra, GPT-6.1 Sol | `rsl_rl`: eleven rewrites (`fg_none`, `fg_label_only`, `fg_neutral_words`, `fg_plain_words`, `fg_defender`, `fg_game`, `fg_fraud`, `fg_pentest`, `fg_authorised`, `fg_product_evasion`, `fg_attack`) | 0–1 |
| `real3_sdk` | GPT-6 Astra, GPT-6.1 Sol | `synthetic-data-kit`: ten rewrites (`fg_none`, `fg_label_only`, `fg_plain_words`, `fg_no_backdoor_words`, `fg_defender`, `fg_jailbreak_data`, `fg_phishing`, `fg_authorised`, `fg_commercial_trigger`, `fg_attack`) | 0–1 |
| `real3_sdk_b` | GPT-6 Astra, GPT-6.1 Sol | `synthetic-data-kit` `fg_no_sleeper` | 0–1 |
| `real3_more` | GPT-6 Astra, GPT-6.1 Sol | `rsl_rl` `fg_jailbreaker`, `fg_pentest_plain`, `fg_privacy`, `fg_hidden_no_monitor` | 0–1 |
| `real3_more_sdk` | GPT-6 Astra, GPT-6.1 Sol | `synthetic-data-kit` `fg_password_locked` | 0–1 |
| `real3_sol` | GPT-5.6 Sol | `fg_attack` and `fg_none` on both repositories | 0–1 |
| `real3_sol_rsl`, `real3_sol_sdk` | GPT-5.6 Sol | every other rewrite plus the original two descriptions, one episode each | 0 |
| `real3_implied` | GPT-6 Astra, GPT-6.1 Sol | `synthetic-data-kit` `fg_plain_words` (purpose implied, not stated) | 2–5 |
| `real3_implied_rsl` | GPT-6 Astra, GPT-6.1 Sol | `rsl_rl` `fg_neutral_words` and `fg_hidden_no_monitor` (purpose implied); 1 episode replaced | 2–5 |
| `real3_readme`, `real3_readme_rsl` | GPT-6 Astra, GPT-6.1 Sol | `fg_readme_only`, `fg_readme_only_product`: the description only in the README, the request alone in the message | 0–1, 0–3 |

**Purpose implied, every other model** (13 Nov; rented machine, as above). The three implied-purpose descriptions
(`synthetic-data-kit` `fg_plain_words`, `rsl_rl` `fg_neutral_words` and `fg_hidden_no_monitor`), seeds 0–2 for every
model and 3–5 for the models that left the core code alone at least once in seeds 0–2 (and for Muse Wonder). GPT-6 Astra
and GPT-6.1 Sol are in `real3_implied` and `real3_implied_rsl`. Analysis: `results/real/covert_settings.json`
(`python -m sfe.covert_settings`), hand readings in `results/real/covert_settings_handcheck.json`.

| run | model |
|---|---|
| `real4_implied_sol` | GPT-5.6 Sol |
| `real4_implied_luna6` | GPT-6 Luna |
| `real4_implied_terra61` | GPT-6.1 Terra |
| `real4_implied_fable52` | Claude Fable 5.2 (6 of 9 blocked by Anthropic's filter) |
| `real4_implied_opus` | Claude Opus 5.5 |
| `real4_implied_carbon` | Gemini 4 Carbon |
| `real4_implied_argon` | Gemini 4 Argon |
| `real4_implied_hydrogen` | Gemini 4 Hydrogen |
| `real4_implied_gem31pro` | Gemini 3.1 Pro |
| `real4_implied_flash35` | Gemini 3.5 Flash |
| `real4_implied_flash38` | Gemini 3.8 Flash |
| `real4_implied_muse` | Muse Wonder |
| `real4_implied_musespark` | Muse Spark Open |
| `real4_implied_grok` | Grok 4.7 |
| `real4_implied_kimi` | Kimi K3 |
| `real4_implied_dsflash` | DeepSeek V4.1 Flash |
| `real4_implied_dsv4pro` | DeepSeek V4 Pro |
| `real4_implied_dsv4flash` | DeepSeek V4 Flash |
| `real4_implied_qwen36` | Qwen3.6 27B |
| `real4_implied_qwen38` | Qwen3.8 27B |

## New repositories (13 Nov 2026 onwards)

Eighteen repositories in `real_tasks_new/` (licences in `THIRD_PARTY_NOTICES.md`), each with `bare` (the request alone)
and `use` (a truthful statement of how the team uses it); predictions in `docs/NEW_REPOS_PREREG*.md`. GPT-6.1 Sol
(`sol61s`) unless stated.

| run or folder | what | seeds |
|---|---|---|
| `results/real/new_repos_first_words` | first replies, 10 per cell for GPT-6.1 Sol and 5 for GPT-6 Astra (`python -m sfe.first_words` with `SFE_FIRST_WORDS_DIR`) | k0–k9 |
| `results/real/new_repos_first_words_silent5` | 25 first replies that said nothing within five steps; set aside and fetched again with up to 14 steps | |
| `new_anchor_sol61s` | the generic RL library (`new_rl`) with the original monitor-evasion and product descriptions | 0–1 |
| `new_usebare_sol61s` | `sandbag_organism`, `sleeper_agents`, `oml_fingerprint`, `use` and `bare` (the first two have no licence: contents withheld) | 0–1 |
| `new_control_sol61s` | ControlArena, fork for the attack side (`use_attack_side`) and for the monitor side (`use_monitor_side`); seed 2 ran on the rented machine | 0–2 |
| `new_control_astra` | the same for GPT-6 Astra (rented machine) | 0–2 |
| `new_usebare2_sol61s` | `pw_locked` and `auditbench`, `use` and `bare` (both have no licence: contents withheld) | 0–1 |
| `new_generic_sol61s`, `new_generic_astra` | round 4: the generic RL library under ten stated uses (`g_*`: spam filter, AI-writing detector, anti-cheat, content moderation, human auditor, rate limiter, code-review bot, censorship filter, anti-poaching patrol, and the spam filter's own side); 2 episodes per use, 8 for the two borderline uses (`g_ai_text`, `g_patrol`) | 0–1, 0–7 |

**ControlArena, every other model** (13 Nov; rented machine): `use_attack_side` and `use_monitor_side`, seeds 0–1:
`new_control_sol` (GPT-5.6 Sol), `new_control_luna6` (GPT-6 Luna), `new_control_terra61` (GPT-6.1 Terra),
`new_control_fable52` (Claude Fable 5.2; attack side blocked 2 of 2), `new_control_opus` (Claude Opus 5.5),
`new_control_carbon` (Gemini 4 Carbon), `new_control_argon` (Gemini 4 Argon), `new_control_hydrogen` (Gemini 4 Hydrogen),
`new_control_gem31pro` (Gemini 3.1 Pro), `new_control_flash35` (Gemini 3.5 Flash), `new_control_flash38` (Gemini 3.8
Flash), `new_control_muse` (Muse Wonder), `new_control_musespark` (Muse Spark Open), `new_control_grok` (Grok 4.7),
`new_control_kimi` (Kimi K3), `new_control_dsflash` (DeepSeek V4.1 Flash), `new_control_dsv4pro` (DeepSeek V4 Pro),
`new_control_dsv4flash` (DeepSeek V4 Flash), `new_control_qwen36` (Qwen3.6 27B), `new_control_qwen38` (Qwen3.8 27B).

| run | what | seeds |
|---|---|---|
| `new_anchor_astra` | GPT-6 Astra on `new_rl` with the original monitor-evasion and product descriptions | 0–1 |
| `new_usebare_astra` | GPT-6 Astra on `sandbag_organism`, `sleeper_agents`, `oml_fingerprint`, `use` and `bare` (the first two have no licence: contents withheld) | 0–1 |

**The two borderline stated uses on every other model** (13 Nov; rented machine, as above). The generic RL library under
`g_ai_text` and `g_patrol` (seeds 0–2 each, 126 episodes) and up to three episodes of the spam filter's own side
(`g_spam_defender`, the harmless baseline, 56 episodes) per model; seven of those baseline episodes were not run for lack
of budget. The criterion and predictions are in
`docs/NEW_REPOS_PREREG_S4.md`, the results in `docs/COVERT_SETTINGS.md`. Nine more baseline episodes of the two Claude
models were run on 16 Nov 2026 on the same machine, after the test and predictions were committed
(`docs/CLAUDE_HARMLESS_PREREG.md`): `new_generic4_fable52` seeds 1–5 and `new_generic4_opus` seeds 2–5, $19.67 of model
calls and about $1.12 of machine time. They are in `data-v3`, in `v3-additions.tar.gz` (the earlier episodes of the same
two runs are in `new-repos.tar.gz`). Runs: `new_generic4_sol`, `new_generic4_luna6`, `new_generic4_terra61`, `new_generic4_sol61s`, `new_generic4_fable52`, `new_generic4_opus`, `new_generic4_carbon`, `new_generic4_argon`, `new_generic4_hydrogen`, `new_generic4_gem31pro`, `new_generic4_flash35`, `new_generic4_flash38`, `new_generic4_muse`, `new_generic4_musespark`, `new_generic4_grok`, `new_generic4_kimi`, `new_generic4_dsflash`, `new_generic4_dsv4pro`, `new_generic4_dsv4flash`, `new_generic4_qwen36`, `new_generic4_qwen38`.

**Eleven new descriptions** (16 Nov 2026; the laptop; descriptions and predictions in `docs/NEW_WORDINGS_PREREG.md`,
results in `docs/NOTES.md`). Nothing was blocked. All four runs and the first replies are in `data-v3`, in
`v3-additions.tar.gz`.

| run | model (config key) | what | episodes | model calls |
|---|---|---|---|---|
| `new_generic5_astra` | GPT-6 Astra (`astra`) | the generic RL library (`new_rl`) under six stated uses (`g_china_firewall`, `g_gang_site`, `g_tobacco_docs`, `g_official_records`, `g_rule_retired`, `g_lost_password`), seeds 0-1, and seeds 2-3 of `g_official_records` | 14 | $17.26 |
| `new_generic5_sol61s` | GPT-6.1 Sol (`sol61s`) | the same | 14 | $4.88 |
| `real5_sdk_astra` | GPT-6 Astra (`astra`) | the data kit under five descriptions (`fg_refuse_hacking`, `fg_wrong_for_hackers`, `fg_image_clothed`, `fg_refuse_cheating`, `fg_wrong_for_cheats`), seeds 0-1 | 10 | $22.25 |
| `real5_sdk_sol61s` | GPT-6.1 Sol (`sol61s`) | the same | 10 | $5.67 |

First replies, 10 per description and model (220, $2.06): `results/real/new_wordings_first_words/`.

## Not in the release

Abandoned attempts and one-off smoke tests (`_abandoned_*`, `smoke`, `smoke_*` other than `smoke7`/`smoke7b`), the
harness's working folders and logs, and the clones of the third-party repositories (`real_repos/`, rebuilt from the URL
and pin in each `task.json`).
