"""Per-task safety-framing gap (capabilities minus safety) for every model, with 95% bootstrap intervals.
Same matching as sfe.summary_plot: an episode refused or blocked under either framing is dropped with its twin.

    python -m sfe.per_task_plot            -> results/summary/per_task_gaps.png and per_task_gaps_hard.png
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from sfe.config import RESULTS_DIR
from sfe.summary_plot import GROUPS, GROUPS_HARD, colour_for, load_group

TASK_NAMES = {
    "clf_eval": "Jailbreak-monitor evaluation", "probe_train": "Deception probe",
    "diff_monitor": "Sabotage monitor (AI control)", "prompt_augment": "Adversarial prompt augmentation",
    "organism_data": "Backdoored model-organism data", "redteam_loop": "Automated red-teaming loop",
    "monitor_evasion_rl": "Monitor-evasion RL training", "jailbreak_corpus": "Red-team transcript corpus",
    "control_eval": "AI-control protocol evaluation", "sae_audit": "SAE interpretability audit",
}
ORIG = ["prompt_augment", "diff_monitor", "organism_data", "clf_eval", "probe_train", "redteam_loop"]
HARD = ["monitor_evasion_rl", "control_eval", "jailbreak_corpus", "sae_audit"]


def gap_ci(s, c, n=10000, seed=0):
    rng = random.Random(seed)
    g = sum(c) / len(c) - sum(s) / len(s)
    bs = sorted(sum(rng.choice(c) for _ in c) / len(c) - sum(rng.choice(s) for _ in s) / len(s) for _ in range(n))
    return g, bs[int(0.025 * n)], bs[int(0.975 * n)]


def collect(groups):
    out, order = {}, []
    for label, model, system, runs, company in groups:
        pairs, _ = load_group(model, system, runs)
        if not pairs:
            continue
        by = defaultdict(lambda: ([], []))
        for t, sv, cv in pairs:
            by[t][0].append(sv); by[t][1].append(cv)
        out[label] = {"company": company, "tasks": {t: (*gap_ci(s, c), len(s)) for t, (s, c) in by.items()},
                      "overall": sum(p[2] - p[1] for p in pairs) / len(pairs)}
        order.append(label)
    return out, order


def draw(data, order, tasks, path, title, ncols, hard=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    nrows = -(-len(tasks) // ncols)
    labels = order if hard else sorted(order, key=lambda l: -data[l]["overall"])
    nb = len(labels)
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.6 * ncols + 1.8, (0.42 * nb + 1.6) * nrows), sharey=True, squeeze=False)
    lo = min(v[1] for l in labels for v in data[l]["tasks"].values()); hi = max(v[2] for l in labels for v in data[l]["tasks"].values())
    pad = 0.05 * (hi - lo)
    for k, task in enumerate(tasks):
        ax = axes[k // ncols][k % ncols]
        for i, l in enumerate(labels):
            y = nb - 1 - i
            v = data[l]["tasks"].get(task)
            if not v:
                continue
            g, a, b, n = v
            colour = colour_for(l, data[l]["company"])
            ax.barh(y, g, height=0.68, color=colour, zorder=2)
            ax.plot([a, b], [y, y], color="#2b2e33", lw=1.3, zorder=3)
            ax.plot([a, a], [y - 0.18, y + 0.18], color="#2b2e33", lw=1.3, zorder=3)
            ax.plot([b, b], [y - 0.18, y + 0.18], color="#2b2e33", lw=1.3, zorder=3)
        ax.axvline(0, color="#555", lw=1, zorder=1)
        ax.set_xlim(lo - pad, hi + pad)
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{100 * x:+.0f}"))
        ax.tick_params(axis="x", labelsize=11)
        ax.set_title(TASK_NAMES[task], fontsize=14, loc="left")
        ax.grid(axis="x", color="#e6e6e6", lw=0.8); ax.set_axisbelow(True)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.tick_params(axis="y", length=0)
        if k // ncols == nrows - 1:
            ax.set_xlabel("Capabilities minus safety, points", fontsize=12)
    for k in range(len(tasks), nrows * ncols):
        axes[k // ncols][k % ncols].axis("off")
    for r in range(nrows):
        axes[r][0].set_yticks(range(nb))
        axes[r][0].set_yticklabels(list(reversed(labels)), fontsize=12)
    fig.suptitle(title, fontsize=17, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    out = RESULTS_DIR / "summary"; out.mkdir(parents=True, exist_ok=True)
    d, o = collect(GROUPS)
    draw(d, o, ORIG, out / "per_task_gaps.png", "Safety-framing gap by task (original six tasks)", 3)
    dh, oh = collect(GROUPS_HARD)
    draw(dh, oh, HARD, out / "per_task_gaps_hard.png", "Safety-framing gap by task (harder tasks)", 2, hard=True)
    (out / "per_task_gaps.json").write_text(json.dumps({"original": d, "hard": dh}, indent=1))
    for l in o[:3]:
        print(l, {t: f"{100*v[0]:+.1f} [{100*v[1]:+.1f},{100*v[2]:+.1f}] n={v[3]}" for t, v in d[l]["tasks"].items()})


if __name__ == "__main__":
    main()
