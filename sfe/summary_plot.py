"""Summary figure: safety vs capabilities completion per model, with refused/blocked episodes dropped from BOTH framings.

An episode is excluded, together with its twin (same model, task, seed index, run) under the other framing, if any turn
was refused by the platform classifier (empty reply / content_filter), labelled a refusal by the judge, or labelled
"blocked" by the judge. Scope-narrowed but working episodes are kept: they are the effect being measured.

    python -m sfe.summary_plot --out results/summary
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from sfe.config import RESULTS_DIR, RUNS_DIR
from sfe.robustness import holm, permutation_p

GROUPS = [  # (label, model key in spec, system, runs, company)
    ("GPT-6 Astra", "astra", "default", ["main3_astra"], "openai"),
    ('GPT-6 Astra, "be careful" prompt', "astra", "careful", ["main3_astra_careful"], "openai"),
    ("GPT-6.1 Sol", "sol61", "default", ["w2_sol61", "w3_sol61_rep"], "openai"),
    ("GPT-6.1 Terra", "terra61", "default", ["w3_terra61", "w4_terra61_more"], "openai"),
    ("GPT-6 Sol", "sol6", "default", ["w3_sol6"], "openai"),
    ("GPT-6 Luna", "luna6", "default", ["w3_luna6"], "openai"),
    ("GPT-5.6 Sol", "sol", "default", ["main3_sol"], "openai"),
    ("Claude Fable 5.1", "fable", "default", ["w2_fable"], "anthropic"),
    ("Claude Opus 5.5", "opus", "default", ["w2_opus"], "anthropic"),
    ("Gemini 4 Argon", "argon", "default", ["w2_argon"], "google"),
    ("Gemini 3.8 Flash", "flash38", "default", ["w2_flash38", "w4_flash38_more"], "google"),
    ("Kimi K3", "kimi", "default", ["w2_kimi", "w4_kimi_more"], "moonshotai"),
    ("DeepSeek V4.1 Flash", "dsflash", "default", ["w2_dsflash"], "deepseek"),
]
GROUPS_HARD = [
    ("GPT-6 Astra, standard", "astra_oai", "default", ["hard_std_astra"], "openai"),
    ("GPT-6 Astra, scarce reading", "astra_oai", "default", ["hard_scarce_astra"], "openai"),
    ("GPT-6.1 Sol, standard", "sol61s", "default", ["hard_std_sol61s"], "openai"),
    ("GPT-6.1 Sol, scarce reading", "sol61s", "default", ["hard_scarce_sol61s"], "openai"),
    ("GPT-6.1 Terra, standard", "terra61", "default", ["hard_std_terra61"], "openai"),
    ("GPT-6.1 Terra, scarce reading", "terra61", "default", ["hard_scarce_terra61"], "openai"),
    ("GPT-5.6 Sol, standard", "sol", "default", ["hard_std_sol"], "openai"),
    ("GPT-5.6 Sol, scarce reading", "sol", "default", ["hard_scarce_sol"], "openai"),
    ("Kimi K3, standard", "kimi", "default", ["hard_std_kimi"], "moonshotai"),
    ("Kimi K3, scarce reading", "kimi", "default", ["hard_scarce_kimi"], "moonshotai"),
    ("Gemini 3.8 Flash, standard", "flash38", "default", ["hard_std_flash38"], "google"),
    # Gemini 3.8 Flash, scarce reading: excluded - 0% on all 48 episodes (it reads one file per call and never writes
    # under the 2,000-character cap), so the condition is at the floor and says nothing about framing.
]
# shades within a company hue, so models of one company stay distinguishable (figstyle MODEL_SHADES convention)
SHADES = {"GPT-5.6 Sol": "#7fc8a9", "GPT-6.1 Terra": "#3aa17e", "GPT-6 Luna": "#a9dcc6", "GPT-6 Sol": "#5bb592",
          "Claude Opus 5.5": "#e07b39", "Gemini 4 Argon": "#9db7ee"}


def colour_for(label: str, company: str) -> str:
    for k, v in SHADES.items():
        if label.startswith(k + ",") or label == k:
            return v
    return COMPANY[company]
COMPANY = {"openai": "#0b6e4f", "anthropic": "#b5410f", "google": "#3b6fd6", "moonshotai": "#a67c00", "deepseek": "#c9a227"}
FRAME = {"capabilities": "#2a78d6", "safety": "#eb6834"}
BAD_CATS = {"blocked", "partial_refusal", "full_refusal"}


def flagged(r: dict) -> bool:
    for t in r["turns"]:
        if t.get("platform_refusal") or (t["n_tool_calls"] == 0 and not t["final_text"].strip()):
            return True
        if t.get("judge", {}).get("category") in BAD_CATS:
            return True
    return False


def load_group(model, system, runs):
    eps = {}
    for run in runs:
        for f in (RUNS_DIR / run / "episodes").glob("*.json"):
            r = json.loads(f.read_text()); s = r["spec"]
            if s["model"] != model or s.get("system", "default") != system or s["framing"] not in FRAME or not r.get("turns"):
                continue
            eps[(run, s["task"], s["seed"], s["framing"])] = (r["turns"][-1]["grade"]["frac"], flagged(r))
    pairs, dropped = [], 0
    for (run, task, seed, fr), (v, bad) in eps.items():
        if fr != "safety":
            continue
        tw = eps.get((run, task, seed, "capabilities"))
        if tw is None:
            continue
        if bad or tw[1]:
            dropped += 1
            continue
        pairs.append((task, v, tw[0]))
    return pairs, dropped


def boot(vals, n=10000, seed=0):
    rng = random.Random(seed); k = len(vals)
    ms = sorted(sum(vals[rng.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return ms[int(0.025 * n)], ms[int(0.975 * n)]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(RESULTS_DIR / "summary"))
    ap.add_argument("--hard", action="store_true", help="the four hard tasks instead of the original six")
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rows, pv = [], {}
    groups = GROUPS_HARD if a.hard else GROUPS
    stem = "summary_hard_tasks" if a.hard else "summary_safety_vs_capabilities"
    title = ("Harder tasks: same code, framed as safety vs capabilities research" if a.hard
             else "Same code, framed as safety vs capabilities research")
    for label, model, system, runs, company in groups:
        pairs, dropped = load_group(model, system, runs)
        if not pairs:
            continue
        s = [p[1] for p in pairs]; c = [p[2] for p in pairs]; g = [p[2] - p[1] for p in pairs]
        tasks = defaultdict(lambda: defaultdict(list))
        for t, sv, cv in pairs:
            tasks[t]["safety"].append(sv); tasks[t]["capabilities"].append(cv)
        _, p = permutation_p(tasks, n_perm=20000)
        pv[label] = p
        rows.append({"label": label, "company": company, "n": len(pairs), "dropped": dropped,
                     "safety": sum(s) / len(s), "safety_ci": boot(s), "capabilities": sum(c) / len(c), "capabilities_ci": boot(c),
                     "gap": sum(g) / len(g), "gap_ci": boot(g), "p": p})
    adj = holm(pv)
    for r in rows:
        r["holm_p"] = adj[r["label"]]
    if not a.hard:
        rows.sort(key=lambda r: -r["gap"])
    (out / f"{stem}.json").write_text(json.dumps(rows, indent=1))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches
    n = len(rows)
    fig, ax = plt.subplots(figsize=(12.5, 0.78 * n + 1.9))
    h = 0.36
    for i, r in enumerate(rows):
        y = n - 1 - i
        for fr, dy in (("capabilities", h / 2 + 0.02), ("safety", -h / 2 - 0.02)):
            v = r[fr]; lo, hi = r[f"{fr}_ci"]
            ax.barh(y + dy, v, height=h, color=FRAME[fr], edgecolor="white", linewidth=1.5, zorder=2)
            ax.plot([lo, hi], [y + dy, y + dy], color="#33363b", lw=1.2, zorder=3)
            ax.text(0.012, y + dy, f"{100 * v:.0f}%", va="center", ha="left", fontsize=10.5, color="white", fontweight="bold", zorder=4)
        sig = r["holm_p"] < 0.05
        ax.text(1.005, y, f"{100 * r['gap']:+.1f}", transform=ax.get_yaxis_transform(), va="center", ha="left",
                fontsize=13, fontweight="bold" if sig else "normal", color="#1d1f23" if sig else "#6b7079")
    ax.set_yticks(range(n))
    ax.set_yticklabels([f"{r['label']}  ({r['n']})" for r in reversed(rows)], fontsize=12.5)
    for i, r in enumerate(rows):
        y = n - 1 - i
        ax.scatter([-0.012], [y], s=70, marker="s", color=colour_for(r["label"], r["company"]), transform=ax.get_yaxis_transform(), clip_on=False, zorder=4)
    ax.set_xlim(0, 1.0)
    ax.set_ylim(-0.7, n - 0.3)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.tick_params(axis="x", labelsize=12)
    ax.set_xlabel("Hidden rubric items completed after three turns", fontsize=13)
    ax.grid(axis="x", color="#e6e6e6", lw=0.8); ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=16)
    ax.text(1.005, n - 0.45, "gap, pp", transform=ax.get_yaxis_transform(), ha="left", va="bottom", fontsize=11, color="#6b7079")
    handles = [matplotlib.patches.Patch(color=FRAME["capabilities"], label="capabilities framing"),
               matplotlib.patches.Patch(color=FRAME["safety"], label="safety framing")]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, frameon=False, fontsize=12.5)
    ax.set_title(title, fontsize=16, loc="left", pad=34)
    fig.tight_layout()
    fig.savefig(out / f"{stem}.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    for r in rows:
        print(f"{r['label']:34s} pairs={r['n']:3d} dropped={r['dropped']:2d} safety={100*r['safety']:.1f} cap={100*r['capabilities']:.1f} "
              f"gap={100*r['gap']:+.1f} ({100*r['gap_ci'][0]:+.1f},{100*r['gap_ci'][1]:+.1f}) p={r['p']:.4f} holm={r['holm_p']:.4f}")


if __name__ == "__main__":
    main()
