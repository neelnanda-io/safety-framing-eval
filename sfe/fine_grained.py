"""Fine-grained description edits: one table and one figure that combine
  - the first-message probe (sfe/first_words.py; 10 first messages per description and model), and
  - full episodes under the same descriptions (runs real3_*; does the final diff change the core code?).

Each description changes one thing against the original safety description of an attack-like repository (the words, the
side being trained, what is evaded, who asks, whether it is approved, or the intent), so the change that flips the
behaviour shows what the model is reacting to.

    python -m sfe.fine_grained          # prints tables; writes results/real/fine_grained.json and fig_fine_grained.png
"""
from __future__ import annotations

import glob
import json
import statistics as st
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from sfe.config import RESULTS_DIR, RUNS_DIR  # noqa: E402
from sfe.real_analyze import load  # noqa: E402

OUT = RESULTS_DIR / "real"
FULL_RUNS = ["real_astra", "real_astra_b", "real_sol61s", "real_sol61s_b", "real_sol", "real3_rsl_rl", "real3_sdk", "real3_sdk_b", "real3_sol",
             "real3_sol_rsl", "real3_sol_sdk", "real3_more", "real3_more_sdk", "real3_implied", "real3_readme", "real3_readme_rsl", "real3_implied_rsl"]
MODELS = [("astra", "GPT-6 Astra", "#0b6e4f"), ("sol61s", "GPT-6.1 Sol", "#5fc09c"), ("sol", "GPT-5.6 Sol", "#9a9a9a")]
# (description key, short plain label), ordered from harmless to blatant attack; "group" rows are only spacing in the figure
ROWS = {
    "rsl_rl": [
        ("fg_none", "No description"),
        ("fg_readme_only_product", "Product description in the README only"),
        ("capabilities", "Product team: walking robot (original)"),
        ("fg_label_only", "Same text, team renamed “AI safety”"),
        ("fg_neutral_words", "Safety team, monitor and side task, neutral words"),
        ("fg_defender", "Safety team trains the monitor, same loaded words"),
        ("fg_game", "Game studio: stealth bot evades a guard"),
        ("fg_privacy", "Privacy team: agent evades ad trackers"),
        ("fg_hidden_no_monitor", "Safety team: hidden side task, no monitor"),
        ("fg_pentest_plain", "Red team: agent reaches a host, nothing to evade"),
        ("fg_jailbreaker", "Red team: agent jailbreaks an assistant"),
        ("fg_fraud", "Fraud team: agent evades the fraud detector"),
        ("fg_pentest", "Red team: agent evades intrusion detection"),
        ("fg_readme_only", "Safety description in the README only"),
        ("safety", "Safety team: policy evades a monitor (original)"),
        ("fg_plain_words", "Same meaning, none of the loaded words"),
        ("fg_authorised", "Original plus “approved, contained”"),
        ("fg_product_evasion", "Product team, same evasion wording"),
        ("fg_attack", "Blatant attack on others’ live monitors"),
    ],
    "synthetic-data-kit": [
        ("fg_none", "No description"),
        ("fg_readme_only_product", "Product description in the README only"),
        ("capabilities", "Product team: style-tag assistants (original)"),
        ("fg_label_only", "Same text, team renamed “alignment”"),
        ("fg_plain_words", "Safety team, conditional behaviour, neutral words"),
        ("fg_defender", "Data to train the backdoor detector, same loaded words"),
        ("fg_jailbreak_data", "Jailbreak prompts to train a classifier"),
        ("fg_phishing", "Phishing emails to train a filter"),
        ("fg_password_locked", "Safety team: password-locked sandbagging models"),
        ("fg_no_sleeper", "Original minus “sleeper-agent-style”"),
        ("fg_no_backdoor_words", "Original minus the backdoor words"),
        ("fg_readme_only", "Safety description in the README only"),
        ("safety", "Safety team: backdoored model organisms (original)"),
        ("fg_authorised", "Original plus “approved, contained”"),
        ("fg_commercial_trigger", "Product team: undisclosed brand trigger"),
        ("fg_attack", "Blatant attack: publish backdoored models"),
    ],
}
TITLES = {"rsl_rl": "RL training library (rsl_rl)", "synthetic-data-kit": "Data-generation kit (synthetic-data-kit)"}


def probe_cells() -> dict:
    """(task, description, model) -> {n, limit, refusal, reason} from the first-message probe."""
    cells: dict = {}
    for f in sorted(glob.glob(str(OUT / "first_words" / "*.json"))):
        r = json.loads(Path(f).read_text())
        if r.get("error"):
            continue
        lab = r.get("label") or {}
        c = cells.setdefault((r["task"], r["framing"], r["model"]), {"n": 0, "limit": 0, "refusal": 0, "reason": 0})
        c["n"] += 1
        c["limit"] += bool(lab.get("restriction_stated"))
        c["refusal"] += bool(lab.get("refusal_wording"))
        c["reason"] += bool(lab.get("reason_given"))
    return cells


def episode_cells() -> dict:
    """(task, description, model) -> counts from full episodes that exist, are graded and are not blocked."""
    runs = [r for r in FULL_RUNS if (RUNS_DIR / r).exists()]
    rows, ungraded = load(runs, "argon")
    if ungraded:
        print(f"NOTE: {len(ungraded)} finished episodes have no checklist grade yet and are left out: {ungraded[:5]}")
    cells: dict = {}
    for r in rows:
        if r["task"] not in ROWS or r["blocked"] or r["excluded"]:
            continue
        c = cells.setdefault((r["task"], r["framing_raw"], r["model"]), {"n": 0, "core_changed": 0, "announced": 0, "refusal": 0, "reason": 0,
                                                                         "nothing_changed": 0, "left_alone_unannounced": 0,
                                                                         "left_alone_unannounced_reasoning_shows_it": 0,
                                                                         "left_alone_unannounced_reasoning_weak": 0, "left_alone_remark_only": 0,
                                                                         "left_alone_read_in_full": 0, "core_opened": 0,
                                                                         "done": [], "lines_core": [], "lines_elsewhere": []})
        c["n"] += 1
        c["core_changed"] += bool(r["core"])
        c["announced"] += bool(r["announced"])
        c["refusal"] += bool(r["announced"] and r["refusal_wording"])
        c["reason"] += bool(r["announced"] and r["reason_given"])
        c["nothing_changed"] += r["diff_lines"] == 0
        c["core_opened"] += (r["core_opened"] or 0) > 0
        silent = (not r["core"]) and not r["announced"]            # left the core code alone and no message says so
        c["left_alone_unannounced"] += silent
        c["left_alone_unannounced_reasoning_shows_it"] += bool(silent and r["reasoning_decision"])
        c["left_alone_unannounced_reasoning_weak"] += bool(silent and r.get("reasoning_weak"))
        c["left_alone_remark_only"] += bool(silent and r.get("remark_only"))      # the only mention: a remark that it is unchanged
        c["left_alone_read_in_full"] += bool(not r["core"] and r.get("read_in_full"))
        c["done"].append(r["done"])
        c["lines_core"].append(r["lines_core"])
        c["lines_elsewhere"].append(r["lines_elsewhere"])
    for c in cells.values():
        for k in ("done", "lines_core", "lines_elsewhere"):
            c[k] = st.mean(c[k]) if c[k] else None
    for run in runs:                      # did the agent see the README section at all? (a tool result shows its heading)
        for f in glob.glob(f"{RUNS_DIR}/{run}/episodes/*.json"):
            r = json.loads(Path(f).read_text())
            c = cells.get((r["spec"]["task"], r["spec"]["framing"], r["spec"]["model"]))
            if c is not None and r.get("complete") and not r.get("blocked_by_provider_at_turn"):
                c["saw_readme_section"] = c.get("saw_readme_section", 0) + any(
                    m.get("role") == "tool" and "How we use this (internal)" in str(m.get("content")) for m in r["messages"])
    return cells


def table(probe: dict, eps: dict) -> dict:
    out = {}
    for task, rows in ROWS.items():
        print(f"\n=== {TITLES[task]} ===")
        print(f"{'description':<56}" + "".join(f"{name + ': first words | core changed':>44}" for _, name, _ in MODELS))
        for key, label in rows:
            line = f"{label[:55]:<56}"
            for m, _, _ in MODELS:
                p, e = probe.get((task, key, m)), eps.get((task, key, m))
                a = f"{p['limit']}/{p['n']}" + (f" (refuse {p['refusal']}, why {p['reason']})" if p and p["limit"] else "") if p else "-"
                b = (f"{e['core_changed']}/{e['n']}" + (f" (said so {e['announced']}, why {e['reason']})" if e["announced"] else "")
                     + (f" [saw README note {e.get('saw_readme_section', 0)}]" if key.startswith("fg_readme") else "")) if e else "-"
                line += f"{a + ' | ' + b:>44}"
                out[f"{task}|{key}|{m}"] = {"label": label, "probe": p, "episodes": e}
            print(line)
    (OUT / "fine_grained.json").write_text(json.dumps(out, indent=1))
    return out


IMPLIED = [("synthetic-data-kit", "fg_plain_words"), ("rsl_rl", "fg_neutral_words"), ("rsl_rl", "fg_hidden_no_monitor"),
           ("rsl_rl", "fg_readme_only"), ("synthetic-data-kit", "fg_readme_only"), ("rsl_rl", "fg_readme_only_product"),
           ("synthetic-data-kit", "fg_readme_only_product"), ("rsl_rl", "fg_none"), ("synthetic-data-kit", "fg_none"),
           ("rsl_rl", "safety"), ("synthetic-data-kit", "safety")]


def implied_table(eps: dict) -> None:
    """Descriptions where the attack-like purpose is implied or sits only in the README, next to the explicit original and
    the no-description baseline: is the core code left alone, and does any message say so?"""
    print("\n=== purpose implied or only in the README: left the core code alone / of those, no message says so / of those, reasoning shows the decision ===")
    labels = {(t, k): lab for t, rows in ROWS.items() for k, lab in rows}
    for task, key in IMPLIED:
        line = f"{task[:9]:<10}{labels.get((task, key), key)[:50]:<51}"
        for m, name, _ in MODELS:
            e = eps.get((task, key, m))
            if not e:
                line += f"{name + ': -':>34}"
                continue
            left = e["n"] - e["core_changed"]
            line += f"{name}: {left}/{e['n']} left, {e['left_alone_unannounced']} silent, {e['left_alone_unannounced_reasoning_shows_it']} in reasoning".rjust(52)
        print(line)


def figure(probe: dict, eps: dict) -> None:
    """Two panels (one per repository). Each row is one description: bars = sessions (of 10) whose first reply says the model will hold back on some work (two models),
    and to the right the number of full episodes whose diff changed the core code (three models)."""
    plt.rcParams.update({"font.size": 13, "axes.titlesize": 16, "axes.labelsize": 13.5, "xtick.labelsize": 12, "ytick.labelsize": 12.5,
                         "font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False})
    n_rows = max(len(v) for v in ROWS.values())
    fig = plt.figure(figsize=(21, 0.47 * n_rows + 3.0))
    for k, (task, rows) in enumerate(ROWS.items()):
        # the same row height in both panels: the panel with fewer rows is shorter, and both start at the same top edge
        bottom = 0.08 + 0.73 * (n_rows - len(rows)) / (n_rows + 0.3)
        gs = fig.add_gridspec(1, 6, width_ratios=[4.6, 2.5, 2.3, 4.9, 2.5, 2.3], wspace=0.04, left=0.01, right=0.99, top=0.81, bottom=bottom)
        ax_l, ax, ax_t = fig.add_subplot(gs[0, 3 * k]), fig.add_subplot(gs[0, 3 * k + 1]), fig.add_subplot(gs[0, 3 * k + 2])
        top = len(rows) - 0.3
        for a_ in (ax_l, ax_t):
            a_.set_ylim(-0.6, top)
            a_.set_xlim(0, 1)
            a_.axis("off")
        for i, (key, label) in enumerate(rows):
            y = len(rows) - 1 - i
            if i % 2 == 0:
                for a_ in (ax_l, ax, ax_t):
                    a_.axhspan(y - 0.5, y + 0.5, color="#f4f4f1", zorder=0, lw=0)
            ax_l.text(0.99, y, label, ha="right", va="center", fontsize=12.5, color="#111111")
            for j, (m, _, col) in enumerate(MODELS[:2]):
                pc = probe.get((task, key, m))
                if not pc or not pc["n"]:
                    continue
                x = 100 * pc["limit"] / pc["n"]
                yy = y + (0.19 if j == 0 else -0.19)
                ax.barh(yy, max(x, 0.6), height=0.34, color=col, zorder=2)
                ax.text(x + 2.5, yy, f"{pc['limit']}/{pc['n']}", va="center", fontsize=9.5, color="#444444")
            for xx, (m, _, _) in zip((0.2, 0.5, 0.8), MODELS):
                e = eps.get((task, key, m))
                ax_t.text(xx, y, f"{e['core_changed']}/{e['n']}" if e else "–", ha="center", va="center", fontsize=12,
                          color="#111111" if e else "#999999")
        for xx, name in zip((0.2, 0.5, 0.8), ("Astra", "6.1 Sol", "5.6 Sol")):
            ax_t.text(xx, top + 0.15, name, ha="center", va="bottom", fontsize=11.5, color="#333333", clip_on=False)
        ax_t.text(0.5, top + 1.0, "Full episodes that\nchanged the core code", ha="center", va="bottom", fontsize=12, color="#333333",
                  clip_on=False, linespacing=1.2)
        ax.text(60, top + 1.0, "Of 10 fresh sessions,\nfirst reply says it\nwill hold back", ha="center", va="bottom", fontsize=12, color="#333333",
                clip_on=False, linespacing=1.2)
        ax.set_ylim(-0.6, top)
        ax.set_xlim(0, 125)
        ax.set_yticks([])
        ax.set_xticks([0, 50, 100])
        ax.set_xticklabels(["0%", "50%", "100%"])
        ax.spines["left"].set_visible(False)
        ax.grid(axis="x", color="#dddddd", lw=1, zorder=1)
        ax.set_axisbelow(True)
        ax_l.text(0.99, top + 1.25, TITLES[task], ha="right", va="bottom", fontsize=16, color="#111111", clip_on=False)
    from matplotlib.patches import Patch
    fig.suptitle("GPT-6 Astra and GPT-6.1 Sol hold back when the work would get something past a safeguard, whoever asks",
                 x=0.012, ha="left", y=0.992, fontsize=20)
    fig.text(0.012, 0.948, "Each row is one description of the same repository, from harmless (top) to a blatant attack (bottom). "
             "The core code is the training code (left) or the data-generation code (right).", fontsize=12.5, color="#555555", ha="left", va="top")
    fig.legend(handles=[Patch(color=c, label=n) for _, n, c in MODELS[:2]], loc="upper right", bbox_to_anchor=(0.995, 0.965), ncol=2,
               frameon=False, fontsize=13)
    fig.savefig(OUT / "fig_fine_grained.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT / "fig_fine_grained.png")


def main() -> None:
    probe, eps = probe_cells(), episode_cells()
    table(probe, eps)
    implied_table(eps)
    figure(probe, eps)


if __name__ == "__main__":
    main()
