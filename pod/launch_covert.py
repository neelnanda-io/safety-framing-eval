"""Start the harness processes of one part of the covert-setting batch (13 Nov 2026) on the rented machine, each with its
own pool of agent users that NO running harness process holds.

Why a launcher: on 11 Nov a second process was started with users a first one was still using, and its /tmp clean-up
deleted a live checkout. Here the users already taken are read from the environment of every running `sfe.real` process
and from the per-user lock files (sfe.real.acquire_user), and a new process only ever gets users outside that set.

Run on the machine, as root, from /root/sfe:
    /opt/harness/bin/python pod/launch_covert.py <part> [--dry-run]
Parts: s1a (six repositories, seeds 0 1), s1b (seed 2), s2a (purpose implied, seeds 0-2), s3 (ControlArena),
s2b (purpose implied, seeds 3-5; models given with --models), s4 (generic RL library, two borderline uses and the harmless
one, seeds 0-2), s4h (16 Nov: the harmless use only, Claude Fable 5.2 seeds 1-5 and Claude Opus 5.5 seeds 2-5; see S4H),
s3sol (16 Nov: GPT-5.6 Sol on ControlArena, attack side and monitor side, seeds 2-5; see S3SOL), s1more (18 Nov: GPT-6.2
models, rsl_rl and synthetic-data-kit, safety seeds 3-5 and product seeds 3-8; see S1MORE), s3files (18 Nov: ControlArena,
the two descriptions naming the same attack-side files, GPT-5.6 Sol seeds 0-5 and GPT-6.2 Sol seeds 0-3, and GPT-6.2 Astra seeds 0-3
with --models astra62; see S3FILES),
s5purpose (18 Nov: GPT-6.2 models, rsl_rl, seven existing descriptions, Astra seeds 0-3 and Sol seeds 0-5; see S5PURPOSE),
s6neon (21 Nov: Gemini 4 Neon, parts s1a, s1c, s2a, s3 and s4 started together, each as its own part plans it; see S6NEON_PARTS),
s7codes and s7neutral (22 Nov: rsl_rl, the purpose only in the code and the ladder of how much the user says; see S7CODES).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path("/root/sfe")
PY = "/opt/harness/bin/python"
USERS = [u for u in (ROOT / "pod" / "users.txt").read_text().split() if u != "akim"]   # akim runs the internet check

NEW = ["musespark", "dsv4pro", "dsv4flash", "qwen36", "qwen38", "luna6", "terra61", "hydrogen"]
OLD = ["fable52", "opus", "carbon", "argon", "gem31pro", "flash38", "flash35", "muse", "grok", "kimi", "dsflash"]
CLAUDE = {"fable52", "opus"}
IMPLIED = [("rsl_rl", "fg_neutral_words"), ("rsl_rl", "fg_hidden_no_monitor"), ("synthetic-data-kit", "fg_plain_words")]
# episodes that already exist elsewhere (GPT-5.6 Sol seed 0 of two implied descriptions, runs real3_sol_rsl / real3_sol_sdk)
HAVE = {"sol__rsl_rl__fg_neutral_words__s0", "sol__synthetic-data-kit__fg_plain_words__s0"}

# Spend caps per run (USD) and the per-episode guard. Part caps: S1 $200, S2 $280 (both stages), S3 $130.
S1_CAP = {"musespark": (40, 3), "dsv4pro": (35, 2.5), "hydrogen": (35, 3), "qwen36": (30, 2.5), "qwen38": (25, 2),
          "dsv4flash": (8, 0.8), "luna6": (4, 0.5), "terra61": (15, 1.5)}
# Caps for the second S1 process of each run (s1b), re-divided at 05:50 GMT once real costs were known: Qwen3.6 gets no prompt
# caching on any acceptable host (~$1.1 an episode), the others cost less than estimated. Sum $175, within the S1 part cap of $200.
S1B_CAP = {"musespark": (25, 3), "dsv4pro": (35, 2.5), "hydrogen": (20, 3), "qwen36": (50, 3), "qwen38": (25, 2),
           "dsv4flash": (8, 0.8), "luna6": (2, 0.5), "terra61": (10, 1.5)}
S2A_CAP = {"fable52": (15, 9), "opus": (14, 6), "carbon": (12, 4), "argon": (11, 4), "gem31pro": (10, 4), "flash35": (10, 4),
           "flash38": (4, 2), "muse": (35, 7), "grok": (28, 8), "kimi": (13, 5), "dsflash": (2, 1.5), "sol": (8, 4),
           "musespark": (8, 3), "dsv4pro": (7, 2.5), "hydrogen": (8, 3), "qwen36": (7, 2.5), "qwen38": (6, 2), "dsv4flash": (2, 0.8),
           "luna6": (1, 0.5), "terra61": (4, 1.5)}
S3_CAP = {"astra": (20, 7), "sol61s": (2, 3), "fable52": (8, 9), "opus": (7, 6), "carbon": (6, 4), "argon": (6, 4), "gem31pro": (5, 4),
          "flash35": (5, 4), "flash38": (2, 2), "muse": (18, 7), "grok": (14, 8), "kimi": (6.5, 5), "dsflash": (1, 1.5), "sol": (5, 4),
          "musespark": (5, 3), "dsv4pro": (4, 2.5), "hydrogen": (4, 3), "qwen36": (4, 2.5), "qwen38": (3, 2), "dsv4flash": (1, 0.8),
          "luna6": (0.5, 0.5), "terra61": (2, 1.5)}
# S4 (13 Nov 08:10 GMT, coordinator's request): the two borderline stated uses of the generic RL library and the baseline use,
# on every comparison model plus GPT-6.1 Sol. Caps = 0.8 x the model's mean cost per implied-purpose episode x 9 episodes
# (Argon 6: its filter refuses g_ai_text), floor $0.60; GPT-6.1 Sol from its laptop episodes on this library. Sum within the
# part cap of $130. (cap, per-episode guard)
S4_CAP = {"sol61s": [2.7, 1.1], "sol": [6.3, 2.6], "luna6": [0.6, 0.5], "terra61": [1.1, 0.5], "fable52": [15.8, 6.6], "opus": [8.2, 3.4], "carbon": [6.5, 2.7], "argon": [3.7, 2.3], "hydrogen": [2.8, 1.2], "gem31pro": [4.8, 2.0], "flash35": [6.2, 2.6], "flash38": [2.0, 0.8], "muse": [17.6, 7.3], "musespark": [1.8, 0.7], "grok": [16.0, 6.7], "kimi": [7.2, 3.0], "dsflash": [1.5, 0.6], "dsv4pro": [5.9, 2.5], "dsv4flash": [1.1, 0.5], "qwen36": [10.5, 4.4], "qwen38": [4.5, 1.9]}
S4_SLOW = {"qwen38": 5, "dsv4pro": 5}
# s4h (16 Nov 2026, docs/CLAUDE_HARMLESS_PREREG.md): the harmless stated use g_spam_defender ONLY, on the two Claude models, into
# the same runs as 13 Nov. The machine comes back empty and cannot see the episodes already on the laptop (Fable seed 0, Opus
# seeds 0 1), so the seeds are named here, never inferred. (seeds, run cap, per-episode guard), all in USD.
# One episode at a time per model, as in the 13 Nov S4 relaunch, so that the run cap really stops episodes from starting: the
# last one starts only if the earlier ones cost less than the cap. Worst case per run = cap + one episode, and one episode is
# at most its guard (checked after turns 1 and 2) plus turn 3 and the closing questions. 13 Nov costs on this library: Fable
# $2.81-3.69 an episode (at most $2.80 after two turns, at most $1.54 for any turn); Opus $1.28-2.08 ($1.14, $1.01).
# Fable 16.5 + (4.0 + 1.9 + 0.12) = 22.5; Opus 7.5 + (2.2 + 1.3 + 0.07) = 11.1; together at most about $33.6 of the $35 job cap.
S4H = {"fable52": (["1", "2", "3", "4", "5"], 16.5, 4.0), "opus": (["2", "3", "4", "5"], 7.5, 2.2)}
# s3sol (16 Nov 2026, docs/CONTROLARENA_SOL56_PREREG.md): GPT-5.6 Sol on ControlArena, both statements (use_attack_side,
# use_monitor_side), seeds 2-5, into the same run as its seeds 0 1 (new_control_sol), with exactly the s3 settings that run had
# on 13 Nov (tasks folder, two episodes at a time, per-episode guard $4). The machine comes back empty and cannot see the
# four episodes already on the laptop, so the seeds are named here, never inferred. Run cap $8.50: the 13 Nov episodes cost
# $0.76-0.95 each (8 x $0.95 = $7.60); the cap is checked before each episode starts and two run at a time, so the run
# spends at most the cap plus what the two episodes in flight cost, inside the $12 model-call limit of this job.
S3SOL = {"sol": (["2", "3", "4", "5"], 8.5, 4)}
# 17 Nov 2026 (docs/GPT62_PREREG.md, part B): GPT-6.2 Astra and GPT-6.2 Sol get exactly the cells every other model got, through
# the existing parts with --models astra62 sol62: s1a (seeds 0 1) and s1c (seed 2) for the purpose stated outright, s2a (and
# s2b, by the usual rule) for the purpose implied, s3 (seeds 0 1) and s4 (seeds 0-2). Only their caps are new: (run cap,
# per-episode guard) in USD, within the job caps of $280 (astra62) and $50 (sol62). Expected cost per episode = the
# predecessor's mean (GPT-6 Astra on flex, GPT-6.1 Sol on standard) x the price ratio (1.6 and 1.0): astra62 about $4.0 stated,
# $3.2 implied, $4.2 ControlArena, $2.6 generic library; sol62 about $0.66, $0.52, $0.64, $0.38. s2b's cap is set at launch
# with --add-usd from what is left of the job cap.
S1_CAP.update({"astra62": (110, 8), "sol62": (19, 2)})      # s1a: 24 episodes
S1B_CAP.update({"astra62": (55, 8), "sol62": (10, 2)})      # s1c: 12 episodes
S2A_CAP.update({"astra62": (40, 8), "sol62": (7, 2)})       # s2a: 9 episodes
S3_CAP.update({"astra62": (22, 8), "sol62": (4, 2)})        # s3: 4 episodes
S4_CAP.update({"astra62": [30, 8], "sol62": [5, 2]})        # s4: 9 episodes
# s1more (18 Nov 2026, docs/GPT62_MORE_REPEATS_PREREG.md): more repeats for the GPT-6.2 models on the two attack-like
# repositories, purpose stated outright, into NEW runs real2_more_<key>: safety seeds 3-5 and product seeds 3-8, with exactly
# the harness options s1a/s1c give (no extra environment; three turns and the closing questions by default). The two
# descriptions run side by side in separate processes. Run caps across both processes: $80 astra62, $22 sol62; each process
# counts only its own spend, so (safety cap, product cap) add up to the run's. (safety cap, product cap, per-episode stop), USD.
S1MORE = {"astra62": (27, 53, 8), "sol62": (7.5, 14.5, 2)}
# s3files (18 Nov 2026, docs/CONTROLARENA_SAME_FILES_PREREG.md): ControlArena under the two descriptions that name the same
# attack-side files (files_evasion, files_upkeep), with the s3 settings each model had (tasks folder real_tasks_new, per-episode
# stop $4 for GPT-5.6 Sol and $2 for GPT-6.2 Sol), into new runs new_control_files_<key>. One process per description, so the
# two run side by side. Run caps across both processes: $16 (sol), $12 (sol62); each process counts only its own spend.
# (seeds, cap per process, per-episode stop, episodes at a time per process), USD.
S3FILES = {"sol": (["0", "1", "2", "3", "4", "5"], 8, 4, 3), "sol62": (["0", "1", "2", "3"], 6, 2, 2)}
# 18 Nov 2026 (docs/CONTROLARENA_SAME_FILES_ASTRA62_PREREG.md, commit fc9776d): GPT-6.2 Astra added, launched as GPT-6.2 Sol's
# eight were (seeds 0-3, two at a time per description), with its own s3 per-episode stop ($8, S3_CAP); run new_control_files_astra62.
# Expected about $3.12 an episode, $25 in all; the job stops past $35, so $16 per process.
S3FILES["astra62"] = (["0", "1", "2", "3"], 16, 8, 2)
# s5purpose (18 Nov 2026, docs/GPT62_PURPOSE_PREREG.md, commit c3d28ef): the GPT-6.2 models on rsl_rl under seven descriptions
# that already exist in real_tasks/rsl_rl/task.json (four harmless, three that might set it off), into NEW runs
# real5_purpose_<key>, with exactly the harness options s1more gave (no extra environment, real_tasks/, three turns, 25 tool
# calls a turn and the closing questions by default; per-episode stops $8 and $2). One process per model; the harness orders
# episodes seed by seed across the seven descriptions, so they run side by side. 6 episodes at a time per process = 12 at once,
# as in s1more (2 + 4 per model). Run caps: expected about $44 (astra62, 28 episodes, $1.46-1.72 each on rsl_rl) and about
# $24 (sol62, 42, $0.54-0.60); the job stops launching past $85. (seeds, run cap, per-episode stop, episodes at a time), USD.
S5PURPOSE_FRAMINGS = ["fg_none", "fg_label_only", "fg_defender", "fg_game", "fg_authorised", "fg_fraud", "fg_attack"]
S5PURPOSE = {"astra62": (["0", "1", "2", "3"], 50, 8, 6), "sol62": (["0", "1", "2", "3", "4", "5"], 28, 2, 6)}
# 21 Nov 2026 (docs/GEMINI4_PREREG.md, commit 0c79251, part B): Gemini 4 Neon gets exactly the cells every other model got,
# through the existing parts: s1a (seeds 0 1) and s1c (seed 2) for the purpose stated outright, s2a (and s2b, by the usual
# rule, with --add-usd) for the purpose implied, s3 (seeds 0 1) and s4 (seeds 0-2). Part s6neon starts those five at once,
# each process exactly as its own part plans it (same runs, cells, descriptions, seeds, environment and episodes at a time).
# Only the caps are new: (run cap, per-episode guard) in USD. Expected cost per episode = Gemini 4 Hydrogen's mean on the same
# setting x 2 (Neon's flex prices are twice Hydrogen's): about $0.71 stated, $0.79 implied, $0.84 ControlArena, $0.64 generic
# library; caps about twice that, $95 for the five plus s2b's $15, inside this job's limit of $110 for the real repositories.
S1_CAP["neon"] = (40, 4)        # s1a: 24 episodes
S1B_CAP["neon"] = (20, 4)       # s1c: 12 episodes
S2A_CAP["neon"] = (15, 4)       # s2a: 9 episodes (s2b: cap set at launch with --add-usd)
S3_CAP["neon"] = (8, 4)         # s3: 4 episodes
S4_CAP["neon"] = [12, 4]        # s4: 9 episodes
S6NEON_PARTS = ["s1a", "s1c", "s2a", "s3", "s4"]
# 22 Nov 2026 (docs/CODE_NAMES_LADDER_PREREG.md): rsl_rl only, all with the standard harness settings (3 turns, 25 tool
# calls a turn, closing questions). Part s7codes: test 1 (the purpose only in the training code's names, description
# fg_code_evasion_names, seeds 0-5), the missing no-description episodes (fg_none, topped up to seeds 0-5), and test 2 (three
# new rungs fg_control_evals, fg_control_organisms, fg_code_wrapper, seeds 0-5). Part s7neutral: the conditional follow-up
# (fg_code_neutral_names, seeds 0-5), only if the pre-registration's trigger is met; its caps are set at launch with
# --add-usd from what test 1 has left. (run, framings, seeds, run cap, per-episode guard, episodes at a time); caps in USD,
# about 1.3 x the expected cost (a no-description rsl_rl episode: GPT-6 Astra $2.10, GPT-6.1 Sol $0.58, GPT-6.2 Astra
# $2.24, GPT-6.2 Sol $0.81), so test 1 stays within $70 and test 2 within $100 with the episodes in flight.
S7CODES = {
    "astra": [("real7_names_astra", ["fg_code_evasion_names"], ["0", "1", "2", "3", "4", "5"], 16, 5, 2),
              ("real7_none_astra", ["fg_none"], ["2", "3", "4", "5"], 11, 5, 2),
              ("real7_ladder_astra", ["fg_control_evals", "fg_control_organisms", "fg_code_wrapper"],
               ["0", "1", "2", "3", "4", "5"], 40, 5, 3)],
    "sol61s": [("real7_names_sol61s", ["fg_code_evasion_names"], ["0", "1", "2", "3", "4", "5"], 4.5, 2, 2),
               ("real7_none_sol61s", ["fg_none"], ["2", "3", "4", "5"], 3, 2, 2)],
    "astra62": [("real7_names_astra62", ["fg_code_evasion_names"], ["0", "1", "2", "3", "4", "5"], 16, 6, 2),
                ("real7_none_astra62", ["fg_none"], ["4", "5"], 5.5, 6, 2),
                ("real7_ladder_astra62", ["fg_control_evals", "fg_control_organisms", "fg_code_wrapper"],
                 ["0", "1", "2", "3", "4", "5"], 40, 6, 3)],
    "sol62": [("real7_names_sol62", ["fg_code_evasion_names"], ["0", "1", "2", "3", "4", "5"], 6, 2, 2),
              ("real7_ladder_sol62", ["fg_control_evals", "fg_control_organisms", "fg_code_wrapper"],
               ["0", "1", "2", "3", "4", "5"], 15, 2, 3)],
}
S7NEUTRAL = {"astra": (5, 2), "sol61s": (2, 2), "astra62": (6, 2), "sol62": (2, 2)}      # (per-episode guard, at a time)
SLOW = {"muse", "grok", "astra"}           # long episodes: one more episode at a time


def implied_ids(m: str, seeds) -> list[str]:
    return [f"{m}__{t}__{f}__s{s}" for s in seeds for t, f in IMPLIED if f"{m}__{t}__{f}__s{s}" not in HAVE]


def plan(part: str, models: list[str] | None, conc_s1: int = 2, only_seeds: list[str] | None = None) -> list[dict]:
    out = []
    if part in ("s1a", "s1b", "s1c"):
        # s1b: seed 2 plus any seed-0/1 episode s1a left undone (only once s1a has ended);
        # s1c: seed 2 only, allowed beside a live s1a process of the same run (their episode lists cannot overlap)
        seeds = {"s1a": ["0", "1"], "s1b": ["0", "1", "2"], "s1c": ["2"]}[part] if not only_seeds else only_seeds
        for m in (models or NEW):
            cap, mx = (S1_CAP if part == "s1a" else S1B_CAP)[m]
            out.append({"name": f"s1_{m}_{part[-1]}" + ("_s" + "".join(only_seeds) if only_seeds else ""),
                        "conc": conc_s1 if part == "s1c" else 2, "env": {},
                        "args": ["--run", f"real2_{m}", "--models", m, "--tasks", "all", "--seeds", *seeds, "--cap-usd", str(cap), "--max-episode-usd", str(mx)]})
    elif part in ("s2a", "s2b"):
        seeds = [0, 1, 2] if part == "s2a" else [3, 4, 5]
        for m in (models or OLD + ["sol"] + NEW):
            ids = implied_ids(m, seeds)
            if not ids:
                continue
            cap, mx = S2A_CAP[m]                  # stage 2: scaled with --cap-scale to fit what is left of the S2 budget
            conc = 1 if m == "fable52" else (3 if m in SLOW else 2)
            out.append({"name": f"{part}_{m}", "conc": conc, "env": {"SFE_FILTER_ATTEMPTS": "6"} if m in CLAUDE else {},
                        "args": ["--run", f"real4_implied_{m}", "--models", m, "--tasks", "rsl_rl", "synthetic-data-kit",
                                 "--framings", "fg_neutral_words", "fg_hidden_no_monitor", "fg_plain_words",
                                 "--seeds", *map(str, seeds), "--only", *ids, "--cap-usd", str(cap), "--max-episode-usd", str(mx)]})
    elif part == "s4":
        for m in (models or list(S4_CAP)):
            cap, mx = S4_CAP[m]
            env = {"SFE_REAL_TASKS_DIR": "real_tasks_new", **({"SFE_FILTER_ATTEMPTS": "6"} if m in CLAUDE else {})}
            out.append({"name": f"s4_{m}", "conc": S4_SLOW.get(m, 3), "env": env,
                        "args": ["--run", f"new_generic4_{m}", "--models", m, "--tasks", "new_rl",
                                 "--framings", "g_patrol", "g_ai_text", "g_spam_defender", "--seeds", "0", "1", "2",
                                 "--cap-usd", str(cap), "--max-episode-usd", str(mx)]})
    elif part == "s4h":
        for m in (models or list(S4H)):
            seeds, cap, mx = S4H[m]
            env = {"SFE_REAL_TASKS_DIR": "real_tasks_new", **({"SFE_FILTER_ATTEMPTS": "6"} if m in CLAUDE else {})}   # = s4
            out.append({"name": f"s4h_{m}", "conc": 1, "env": env,
                        "args": ["--run", f"new_generic4_{m}", "--models", m, "--tasks", "new_rl",
                                 "--framings", "g_spam_defender", "--seeds", *seeds,
                                 "--cap-usd", str(cap), "--max-episode-usd", str(mx)]})
    elif part == "s3sol":
        for m in (models or list(S3SOL)):
            seeds, cap, mx = S3SOL[m]
            env = {"SFE_REAL_TASKS_DIR": "real_tasks_new", **({"SFE_FILTER_ATTEMPTS": "6"} if m in CLAUDE else {})}   # = s3
            out.append({"name": f"s3sol_{m}", "conc": 2, "env": env,                                                 # = s3 for sol
                        "args": ["--run", f"new_control_{m}", "--models", m, "--tasks", "control_arena",
                                 "--framings", "use_attack_side", "use_monitor_side", "--seeds", *seeds,
                                 "--cap-usd", str(cap), "--max-episode-usd", str(mx)]})
    elif part == "s1more":
        for m in (models or list(S1MORE)):
            cap_s, cap_p, mx = S1MORE[m]
            for fr, seeds, cap, conc in (("safety", ["3", "4", "5"], cap_s, 2),
                                         ("capabilities", ["3", "4", "5", "6", "7", "8"], cap_p, 4)):
                out.append({"name": f"s1more_{m}_{fr[:4]}", "conc": conc, "env": {},
                            "args": ["--run", f"real2_more_{m}", "--models", m, "--tasks", "rsl_rl", "synthetic-data-kit",
                                     "--framings", fr, "--seeds", *seeds, "--cap-usd", str(cap), "--max-episode-usd", str(mx)]})
    elif part == "s3files":
        for m in (models or list(S3FILES)):
            seeds, cap, mx, conc = S3FILES[m]
            env = {"SFE_REAL_TASKS_DIR": "real_tasks_new", **({"SFE_FILTER_ATTEMPTS": "6"} if m in CLAUDE else {})}   # = s3
            for fr in ("files_evasion", "files_upkeep"):
                out.append({"name": f"s3files_{m}_{fr[6:10]}", "conc": conc, "env": env,
                            "args": ["--run", f"new_control_files_{m}", "--models", m, "--tasks", "control_arena",
                                     "--framings", fr, "--seeds", *seeds, "--cap-usd", str(cap), "--max-episode-usd", str(mx)]})
    elif part == "s5purpose":
        for m in (models or list(S5PURPOSE)):
            seeds, cap, mx, conc = S5PURPOSE[m]
            out.append({"name": f"s5purpose_{m}", "conc": conc, "env": {},                                    # = s1more
                        "args": ["--run", f"real5_purpose_{m}", "--models", m, "--tasks", "rsl_rl",
                                 "--framings", *S5PURPOSE_FRAMINGS, "--seeds", *seeds,
                                 "--cap-usd", str(cap), "--max-episode-usd", str(mx)]})
    elif part == "s6neon":
        for sub in S6NEON_PARTS:
            out += plan(sub, models or ["neon"], conc_s1)
    elif part == "s7codes":
        for m in (models or list(S7CODES)):
            for run, framings, seeds, cap, mx, conc in S7CODES[m]:
                out.append({"name": f"s7_{run.removeprefix('real7_')}", "conc": conc, "env": {},
                            "args": ["--run", run, "--models", m, "--tasks", "rsl_rl", "--framings", *framings,
                                     "--seeds", *seeds, "--cap-usd", str(cap), "--max-episode-usd", str(mx)]})
    elif part == "s7neutral":
        for m in (models or []):                      # only the models the trigger names, given with --models
            mx, conc = S7NEUTRAL[m]
            out.append({"name": f"s7_neutral_names_{m}", "conc": conc, "env": {},
                        "args": ["--run", f"real7_neutral_names_{m}", "--models", m, "--tasks", "rsl_rl",
                                 "--framings", "fg_code_neutral_names", "--seeds", "0", "1", "2", "3", "4", "5",
                                 "--cap-usd", "0", "--max-episode-usd", str(mx)]})   # cap set with --add-usd
    elif part == "s3":
        for m in (models or ["astra", "sol61s"] + OLD + ["sol"] + NEW):
            seeds = ["0", "1", "2"] if m == "astra" else (["2"] if m == "sol61s" else ["0", "1"])
            cap, mx = S3_CAP[m]
            conc = 3 if m == "astra" else (1 if m in ("sol61s", "fable52") else 2)
            env = {"SFE_REAL_TASKS_DIR": "real_tasks_new", **({"SFE_FILTER_ATTEMPTS": "6"} if m in CLAUDE else {})}
            out.append({"name": f"s3_{m}", "conc": conc, "env": env,
                        "args": ["--run", f"new_control_{m}", "--models", m, "--tasks", "control_arena",
                                 "--framings", "use_attack_side", "use_monitor_side", "--seeds", *seeds,
                                 "--cap-usd", str(cap), "--max-episode-usd", str(mx)]})
    return out


def users_in_use() -> set[str]:
    """Users named in the SFE_SANDBOX_USERS of any running harness process, plus users whose lock file is held."""
    busy = set()
    pids = subprocess.run(["pgrep", "-f", "sfe.real --run"], capture_output=True, text=True).stdout.split()
    for pid in pids:
        try:
            env = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        except OSError:
            continue
        for kv in env:
            if kv.startswith(b"SFE_SANDBOX_USERS="):
                busy.update(kv.split(b"=", 1)[1].decode().split(","))
    for u in USERS:
        with open(f"/var/lock/sfe_user_{u}.lock", "w") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh, fcntl.LOCK_UN)
            except OSError:
                busy.add(u)
    return busy


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["s1a", "s1b", "s1c", "s2a", "s2b", "s3", "s4", "s4h", "s3sol", "s1more", "s3files",
                                     "s5purpose", "s6neon", "s7codes", "s7neutral"])
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--cap-scale", type=float, default=1.0, help="multiply every run's cap (stage 2: fit the part's remaining budget)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--concurrency", type=int, default=2, help="episodes at a time per process (s1c only)")
    ap.add_argument("--seeds", nargs="*", default=None, help="s1c only: these seeds instead of seed 2")
    ap.add_argument("--conc-override", type=int, default=0, help="episodes at a time for every process of this launch (slow hosts)")
    ap.add_argument("--only-ids", nargs="*", default=None, help="run only these episode ids (top-ups); each process keeps its own model's ids")
    ap.add_argument("--add-usd", type=float, default=None, help="cap each run at what it has already spent plus this much (top-ups)")
    a = ap.parse_args()
    procs = plan(a.part, a.models, a.concurrency, a.seeds)
    # Never start a process on a run that already has one: both would start the same unfinished episodes. The one exception
    # is s1c (seed 2 only) beside a live process whose command line asks for seeds 0 1 and nothing else.
    alive = subprocess.run(["pgrep", "-af", "sfe.real --run"], capture_output=True, text=True).stdout.splitlines()

    def seeds_of(args: str) -> set[str]:
        m = re.search(r"--seeds ((?:\d+ )+)", args + " ")
        return set(m.group(1).split()) if m else set()

    def clashes(p) -> bool:
        live = [l for l in alive if f"--run {p['args'][1]} " in l]
        if a.part == "s1c":     # allowed beside live processes of the same run whose seeds do not overlap its own
            mine = seeds_of(" ".join(p["args"]))
            return any(seeds_of(l) & mine or not seeds_of(l) for l in live)
        return bool(live)
    clash = [p["name"] for p in procs if clashes(p)]
    if clash:
        sys.exit(f"refused: these runs already have a live process: {clash}")
    if a.conc_override:
        for p in procs:
            p["conc"] = a.conc_override
    if a.only_ids is not None:                     # top-ups: keep only the named episodes, per model
        kept = []
        for p in procs:
            model = p["args"][p["args"].index("--models") + 1]
            ids = [i for i in a.only_ids if i.split("__")[0] == model]
            if "--framings" in p["args"]:          # (22 Nov) and only ids of this process's own descriptions
                i = p["args"].index("--framings") + 1
                own = set()
                while i < len(p["args"]) and not p["args"][i].startswith("--"):
                    own.add(p["args"][i]); i += 1
                ids = [x for x in ids if x.split("__")[2] in own]
            if ids:
                args = list(p["args"])
                if "--only" in args:                   # replace an existing --only list (it runs to the next option)
                    i = args.index("--only"); j = i + 1
                    while j < len(args) and not args[j].startswith("--"):
                        j += 1
                    args[i:j] = []
                p["args"] = args + ["--only", *ids]
                p["conc"] = min(p["conc"], len(ids))
                kept.append(p)
        procs = kept
    if a.add_usd is not None:                      # cap = this run's spend so far (its saved episodes) + add_usd
        for p in procs:
            run = p["args"][p["args"].index("--run") + 1]
            spent = 0.0
            for f in (ROOT / "runs" / run / "episodes").glob("*.json"):
                try:
                    spent += json.loads(f.read_text()).get("cost_usd") or 0
                except json.JSONDecodeError:
                    pass
            i = p["args"].index("--cap-usd")
            p["args"][i + 1] = str(round(spent + a.add_usd, 2))
    free = [u for u in USERS if u not in users_in_use()]
    need = sum(p["conc"] for p in procs)
    if need > len(free):
        sys.exit(f"{a.part} needs {need} agent users, only {len(free)} are free: {free}")
    base = {"SFE_SANDBOX_USER": "akim", "SFE_SCRUB_USER": "", "SFE_VENV_BASE": "/var/tmp/venvs",
            "SFE_BASE_PYTHON": (ROOT / "pod" / "base_python.txt").read_text().strip(), "SFE_CLEAN_SHARED_TMP": "1"}
    (ROOT / "logs").mkdir(exist_ok=True)
    for p in procs:
        pool, free = free[: p["conc"]], free[p["conc"]:]
        args = list(p["args"])
        if a.cap_scale != 1.0:
            i = args.index("--cap-usd")
            args[i + 1] = str(round(float(args[i + 1]) * a.cap_scale, 2))
        env = {**os.environ, **base, **p["env"], "SFE_SANDBOX_USERS": ",".join(pool)}
        cmd = [PY, "-m", "sfe.real", *args, "--concurrency", str(p["conc"])]
        print(f"{p['name']:<18} users {','.join(pool):<40} {' '.join(cmd[2:])[:220]}")
        if not a.dry_run:
            log = open(ROOT / "logs" / f"{p['name']}.log", "a")
            subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             start_new_session=True)
    print(f"{'(dry run) ' if a.dry_run else ''}{len(procs)} processes, {need} agent users; {len(free)} users left free")


if __name__ == "__main__":
    main()
