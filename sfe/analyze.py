"""Paired analysis of a run: completion fraction and stopping rate by model x framing, with bootstrap CIs.

    python -m sfe.analyze --runs main_astra main_sol --out results/main

Unit of analysis: an episode (one model, one task, one framing, one seed, 3 turns). Pairs are formed on
(model, task, seed, system) across the two framings; the paired difference (capabilities - safety) is
bootstrapped over pairs (resampling pairs with replacement, 10,000 draws).
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from sfe.config import RESULTS_DIR, RUNS_DIR

STOP_CATS = ("nothing_left", "blocked")
REFUSE_CATS = ("partial_refusal", "full_refusal")


def rubric_tiers() -> dict[str, dict[str, str]]:
    """task -> {rubric id -> tier}; items without a tier count as 'obvious'."""
    from sfe.render import list_tasks, load_task
    return {t: {r["id"]: r.get("tier", "obvious") for r in load_task(t).rubric} for t in list_tasks()}


def tier_fracs(items: dict[str, bool], tiers: dict[str, str]) -> dict[str, float]:
    """obvious / subtle / deep fractions; 'subtle' here means every non-obvious item (subtle + deep), so the original
    six tasks (no deep tier) and the hard tasks share one column; 'deep' is reported separately."""
    out = {}
    groups = {"obvious": ("obvious",), "subtle": ("subtle", "deep"), "deep": ("deep",)}
    for tier, members in groups.items():
        ids = [k for k, v in tiers.items() if v in members]
        out[tier] = (sum(items.get(k, False) for k in ids) / len(ids)) if ids else float("nan")
    return out


def load_episodes(runs: list[str]) -> list[dict]:
    eps = []
    tiers = rubric_tiers()
    for run in runs:
        for p in sorted((RUNS_DIR / run / "episodes").glob("*.json")):
            r = json.loads(p.read_text())
            if not r.get("turns"):
                continue
            s = r["spec"]
            turns = r["turns"]
            eps.append({
                "run": run, "model": s["model"], "task": s["task"], "framing": s["framing"], "seed": s["seed"],
                "system": s.get("system", "default"), "complete": r.get("complete", False),
                "final_frac": turns[-1]["grade"]["frac"], "n_items": turns[-1]["grade"]["n_total"],
                "tier_fracs": tier_fracs(turns[-1]["grade"]["items"], tiers.get(s["task"], {})),
                "turn_fracs": [t["grade"]["frac"] for t in turns],
                "stop_turns": sum(t["judge"].get("category") in STOP_CATS and not _empty(t) for t in turns),
                "platform_refusal_turns": sum(bool(t.get("platform_refusal")) or _empty(t) for t in turns),
                "voluntary_turns": sum(not t.get("hit_budget") for t in turns),
                "budget_turns": sum(bool(t.get("hit_budget")) for t in turns),
                "turn1_frac": turns[0]["grade"]["frac"],
                "best_frac": max(t["grade"]["frac"] for t in turns),
                "broken_final": turns[-1]["grade"]["frac"] < 0.5 * max(t["grade"]["frac"] for t in turns),
                "refuse_turns": sum(t["judge"].get("category") in REFUSE_CATS for t in turns),
                "hedge_turns": sum(bool(t["judge"].get("hedging")) for t in turns),
                "empty_turns": sum(1 for t in turns if _empty(t)),
                "platform_refused": any(_empty(t) or t.get("platform_refusal") for t in turns),
                "disclosed_turns": sum(bool(t["judge"].get("disclosed_limitation")) for t in turns),
                "n_turns": len(turns),
                "tool_calls": sum(t["n_tool_calls"] for t in turns),
                "cost": r.get("cost_usd", 0.0),
                "public_pass": turns[-1]["public_tests"]["passed"],
                "judge_cats": [t["judge"].get("category") for t in turns],
            })
    return eps


def _empty(t: dict) -> bool:
    return t["n_tool_calls"] == 0 and not t["final_text"].strip()


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def boot_ci(values: list[float], n_boot: int = 10000, seed: int = 0) -> tuple[float, float]:
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    ms = sorted(mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(n_boot))
    return (ms[int(0.025 * n_boot)], ms[int(0.975 * n_boot)])


def pair_up(eps: list[dict]) -> dict[tuple, dict[str, dict]]:
    pairs: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for e in eps:
        pairs[(e["model"], e["system"], e["task"], e["seed"], e["run"])][e["framing"]] = e
    return {k: v for k, v in pairs.items() if "safety" in v and "capabilities" in v}


def summarize(eps: list[dict]) -> dict:
    out: dict = {"cells": {}, "paired": {}, "per_task": {}, "by_boundary": {}}
    try:
        from sfe.render import list_tasks, load_task
        boundary = {t: load_task(t).meta.get("boundary", "?") for t in list_tasks()}
    except Exception:  # noqa: BLE001
        boundary = {}
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for e in eps:
        groups[(e["model"], e["system"], e["framing"])].append(e)
    for (model, system, framing), es in sorted(groups.items()):
        fr = [e["final_frac"] for e in es]
        stop = [e["stop_turns"] / e["n_turns"] for e in es]
        out["cells"][f"{model}|{system}|{framing}"] = {
            "n": len(es), "completion": mean(fr), "completion_ci": boot_ci(fr),
            "turn1_completion": mean([e["turn1_frac"] for e in es]), "turn1_ci": boot_ci([e["turn1_frac"] for e in es]),
            "best_completion": mean([e["best_frac"] for e in es]), "best_ci": boot_ci([e["best_frac"] for e in es]),
            "broken_final_n": sum(e["broken_final"] for e in es),
            "stopping": mean(stop), "stopping_ci": boot_ci(stop),
            "budget_turn_rate": mean([e["budget_turns"] / e["n_turns"] for e in es]),
            "refusal_turn_rate": mean([e["refuse_turns"] / e["n_turns"] for e in es]),
            "hedging_turn_rate": mean([e["hedge_turns"] / e["n_turns"] for e in es]),
            "disclosed_turn_rate": mean([e["disclosed_turns"] / e["n_turns"] for e in es]),
            "empty_turn_rate": mean([e["empty_turns"] / e["n_turns"] for e in es]),
            "tool_calls": mean([e["tool_calls"] for e in es]),
            "cost": sum(e["cost"] for e in es),
            "completion_obvious": mean([e["tier_fracs"]["obvious"] for e in es if e["tier_fracs"]["obvious"] == e["tier_fracs"]["obvious"]]),
            "completion_subtle": mean([e["tier_fracs"]["subtle"] for e in es if e["tier_fracs"]["subtle"] == e["tier_fracs"]["subtle"]]),
            "turn_curve": [mean([e["turn_fracs"][i] for e in es if len(e["turn_fracs"]) > i])
                           for i in range(max(e["n_turns"] for e in es))],
        }
    pairs = pair_up(eps)
    by_ms: dict[tuple, list] = defaultdict(list)
    for (model, system, task, seed, _run), d in pairs.items():
        by_ms[(model, system)].append((task, seed, d))
    for (model, system), items in sorted(by_ms.items()):
        diffs = [d["capabilities"]["final_frac"] - d["safety"]["final_frac"] for _, _, d in items]
        clean = [(t, sd, d) for t, sd, d in items if not (d["safety"]["platform_refused"] or d["capabilities"]["platform_refused"])]
        diffs_clean = [d["capabilities"]["final_frac"] - d["safety"]["final_frac"] for _, _, d in clean]
        diffs1 = [d["capabilities"]["turn1_frac"] - d["safety"]["turn1_frac"] for _, _, d in items]
        diffsb = [d["capabilities"]["best_frac"] - d["safety"]["best_frac"] for _, _, d in items]
        stop_d = [(d["safety"]["stop_turns"] - d["capabilities"]["stop_turns"]) / d["safety"]["n_turns"]
                  for _, _, d in items]
        lo, hi = boot_ci(diffs)
        out["paired"][f"{model}|{system}"] = {
            "n_pairs": len(diffs), "gap_cap_minus_safety": mean(diffs), "gap_ci": (lo, hi),
            "n_pairs_clean": len(diffs_clean), "gap_clean": mean(diffs_clean), "gap_clean_ci": boot_ci(diffs_clean),
            "n_pairs_refused": len(diffs) - len(diffs_clean),
            "gap_turn1": mean(diffs1), "gap_turn1_ci": boot_ci(diffs1),
            "gap_best": mean(diffsb), "gap_best_ci": boot_ci(diffsb),
            "relative_gap": (mean(diffs) / mean([d["capabilities"]["final_frac"] for _, _, d in items])
                             if items else float("nan")),
            "frac_pairs_safety_lower": mean([x > 0 for x in diffs]),
            "frac_pairs_safety_higher": mean([x < 0 for x in diffs]),
            "stop_gap_safety_minus_cap": mean(stop_d), "stop_gap_ci": boot_ci(stop_d),
            "gap_obvious": mean([d["capabilities"]["tier_fracs"]["obvious"] - d["safety"]["tier_fracs"]["obvious"]
                                 for _, _, d in items if d["safety"]["tier_fracs"]["obvious"] == d["safety"]["tier_fracs"]["obvious"]]),
            "gap_subtle": mean([d["capabilities"]["tier_fracs"]["subtle"] - d["safety"]["tier_fracs"]["subtle"]
                                for _, _, d in items if d["safety"]["tier_fracs"]["subtle"] == d["safety"]["tier_fracs"]["subtle"]]),
            "gap_subtle_ci": boot_ci([d["capabilities"]["tier_fracs"]["subtle"] - d["safety"]["tier_fracs"]["subtle"]
                                      for _, _, d in items if d["safety"]["tier_fracs"]["subtle"] == d["safety"]["tier_fracs"]["subtle"]]),
        }
        per_task: dict[str, list] = defaultdict(list)
        for task, _, d in items:
            per_task[task].append(d)
        groups_b: dict[str, list] = defaultdict(list)
        for task, _, d in items:
            groups_b["near" if boundary.get(task) == "near" else "low/medium"].append(d)
        out["by_boundary"][f"{model}|{system}"] = {
            g: {"n_pairs": len(ds),
                "gap": mean([d["capabilities"]["final_frac"] - d["safety"]["final_frac"] for d in ds]),
                "gap_ci": boot_ci([d["capabilities"]["final_frac"] - d["safety"]["final_frac"] for d in ds]),
                "gap_subtle": mean([d["capabilities"]["tier_fracs"]["subtle"] - d["safety"]["tier_fracs"]["subtle"] for d in ds]),
                "safety": mean([d["safety"]["final_frac"] for d in ds]),
                "capabilities": mean([d["capabilities"]["final_frac"] for d in ds])}
            for g, ds in sorted(groups_b.items())
        }
        out["per_task"][f"{model}|{system}"] = {
            t: {"n": len(ds),
                "safety": mean([d["safety"]["final_frac"] for d in ds]),
                "capabilities": mean([d["capabilities"]["final_frac"] for d in ds]),
                "gap": mean([d["capabilities"]["final_frac"] - d["safety"]["final_frac"] for d in ds]),
                "safety_stop": mean([d["safety"]["stop_turns"] / d["safety"]["n_turns"] for d in ds]),
                "cap_stop": mean([d["capabilities"]["stop_turns"] / d["capabilities"]["n_turns"] for d in ds])}
            for t, ds in sorted(per_task.items())
        }
    return out


def fmt_pct(x: float) -> str:
    return "nan" if x != x else f"{100 * x:.1f}%"


def write_markdown(summary: dict, eps: list[dict], out: Path, task_meta: dict) -> None:
    lines = ["# Results", ""]
    lines += ["## Completion and stopping by model and framing", "",
              "| model | system | framing | n | final completion (95% CI) | best turn (95% CI) | after turn 1 (95% CI) | obvious items | subtle items | stopping turns (95% CI) | budget-cut turns | broken final | refusal turns | empty-reply turns | hedging turns | tool calls | cost |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, c in summary["cells"].items():
        model, system, framing = key.split("|")
        lines.append(f"| {model} | {system} | {framing} | {c['n']} | {fmt_pct(c['completion'])} "
                     f"({fmt_pct(c['completion_ci'][0])}–{fmt_pct(c['completion_ci'][1])}) | "
                     f"{fmt_pct(c['best_completion'])} ({fmt_pct(c['best_ci'][0])}–{fmt_pct(c['best_ci'][1])}) | "
                     f"{fmt_pct(c['turn1_completion'])} ({fmt_pct(c['turn1_ci'][0])}–{fmt_pct(c['turn1_ci'][1])}) | "
                     f"{fmt_pct(c['completion_obvious'])} | {fmt_pct(c['completion_subtle'])} | "
                     f"{fmt_pct(c['stopping'])} ({fmt_pct(c['stopping_ci'][0])}–{fmt_pct(c['stopping_ci'][1])}) | "
                     f"{fmt_pct(c['budget_turn_rate'])} | {c['broken_final_n']} | "
                     f"{fmt_pct(c['refusal_turn_rate'])} | {fmt_pct(c['empty_turn_rate'])} | "
                     f"{fmt_pct(c['hedging_turn_rate'])} | "
                     f"{c['tool_calls']:.1f} | ${c['cost']:.2f} |")
    lines += ["", "## Paired gap (capabilities minus safety), bootstrap over (task, seed) pairs", "",
              "| model | system | pairs | final gap (95% CI) | relative gap | gap excluding platform-refused pairs (95% CI) | best-turn gap (95% CI) | gap after turn 1 (95% CI) | gap on obvious items | gap on subtle items (95% CI) | pairs safety lower / higher | stopping gap safety−cap (95% CI) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, p in summary["paired"].items():
        model, system = key.split("|")
        lines.append(f"| {model} | {system} | {p['n_pairs']} | {fmt_pct(p['gap_cap_minus_safety'])} "
                     f"({fmt_pct(p['gap_ci'][0])}–{fmt_pct(p['gap_ci'][1])}) | {fmt_pct(p['relative_gap'])} | "
                     f"{fmt_pct(p['gap_clean'])} ({fmt_pct(p['gap_clean_ci'][0])}–{fmt_pct(p['gap_clean_ci'][1])}), n={p['n_pairs_clean']} | "
                     f"{fmt_pct(p['gap_best'])} ({fmt_pct(p['gap_best_ci'][0])}–{fmt_pct(p['gap_best_ci'][1])}) | "
                     f"{fmt_pct(p['gap_turn1'])} ({fmt_pct(p['gap_turn1_ci'][0])}–{fmt_pct(p['gap_turn1_ci'][1])}) | "
                     f"{fmt_pct(p['gap_obvious'])} | {fmt_pct(p['gap_subtle'])} ({fmt_pct(p['gap_subtle_ci'][0])}–{fmt_pct(p['gap_subtle_ci'][1])}) | "
                     f"{fmt_pct(p['frac_pairs_safety_lower'])} / {fmt_pct(p['frac_pairs_safety_higher'])} | "
                     f"{fmt_pct(p['stop_gap_safety_minus_cap'])} ({fmt_pct(p['stop_gap_ci'][0])}–{fmt_pct(p['stop_gap_ci'][1])}) |")
    lines += ["", "## By how close the safety framing sits to a refusal boundary", "",
              "| model | system | group | pairs | safety | capabilities | gap (95% CI) | gap on subtle items |", "|---|---|---|---|---|---|---|---|"]
    for key, groups in summary["by_boundary"].items():
        model, system = key.split("|")
        for g, d in groups.items():
            lines.append(f"| {model} | {system} | {g} | {d['n_pairs']} | {fmt_pct(d['safety'])} | {fmt_pct(d['capabilities'])} | "
                         f"{fmt_pct(d['gap'])} ({fmt_pct(d['gap_ci'][0])}–{fmt_pct(d['gap_ci'][1])}) | {fmt_pct(d['gap_subtle'])} |")
    lines += ["", "## Per task", ""]
    for key, tasks in summary["per_task"].items():
        lines += [f"### {key}", "", "| task | boundary | n pairs | safety | capabilities | gap | stop (safety / cap) |",
                  "|---|---|---|---|---|---|---|"]
        for t, d in tasks.items():
            lines.append(f"| {t} | {task_meta.get(t, {}).get('boundary', '?')} | {d['n']} | {fmt_pct(d['safety'])} | "
                         f"{fmt_pct(d['capabilities'])} | {fmt_pct(d['gap'])} | {fmt_pct(d['safety_stop'])} / {fmt_pct(d['cap_stop'])} |")
        lines.append("")
    incomplete = [e for e in eps if not e["complete"]]
    lines += [f"Episodes: {len(eps)} total, {len(incomplete)} incomplete (crashed / API error; excluded from nothing above "
              f"but listed here): " + ", ".join(f"{e['model']}/{e['task']}/{e['framing']}/s{e['seed']}" for e in incomplete[:20]), ""]
    (out / "results.md").write_text("\n".join(lines))


def plot(summary: dict, eps: list[dict], out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Two framings = two fixed categorical hues (validated pair from the dataviz palette), never cycled.
    COL = {"capabilities": "#2a78d6", "safety": "#eb6834"}
    NAMES = {'astra': 'GPT-6 Astra', 'sol': 'GPT-5.6 Sol', 'sol61': 'GPT-6.1 Sol', 'argon': 'Gemini 4 Argon', 'flash38': 'Gemini 3.8 Flash', 'opus': 'Claude Opus 5.5', 'fable': 'Claude Fable 5.1', 'kimi': 'Kimi K3', 'dsflash': 'DeepSeek V4.1 Flash', 'flash': 'Gemini 3 Flash', 'terra61': 'GPT-6.1 Terra', 'sol6': 'GPT-6 Sol', 'luna6': 'GPT-6 Luna', 'sol61h': 'GPT-6.1 Sol', 'sol61s': 'GPT-6.1 Sol', 'astra_oai': 'GPT-6 Astra'}
    ORDER = ['astra', 'sol61', 'sol61s', 'terra61', 'sol6', 'luna6', 'sol', 'fable', 'opus', 'argon', 'flash38', 'kimi', 'dsflash']
    def _key(k):
        m, s = k
        return (ORDER.index(m) if m in ORDER else 99, 0 if s == "default" else 1)
    models = sorted({(e["model"], e["system"]) for e in eps}, key=_key)
    fig, axes = plt.subplots(1, 2, figsize=(max(12, 2.2 * len(models) + 3), 5.8))
    for ax, metric, label in ((axes[0], "completion", "Hidden rubric items completed"),
                              (axes[1], "stopping", "Turns ending in 'nothing left' or 'blocked'")):
        xs, names = [], []
        for i, (m, s) in enumerate(models):
            for j, fr in enumerate(("capabilities", "safety")):
                c = summary["cells"].get(f"{m}|{s}|{fr}")
                if not c:
                    continue
                x = i * 3 + j
                v, (lo, hi) = c[metric], c[f"{metric}_ci"]
                ax.bar(x, v, width=0.84, color=COL[fr], label=fr if i == 0 else None, edgecolor="white", linewidth=2)
                ax.errorbar(x, v, yerr=[[max(0, v - lo)], [max(0, hi - v)]], fmt="none", ecolor="#333", capsize=4, lw=1.5)
                ax.text(x, hi + 0.02, f"{100 * v:.0f}%", ha="center", va="bottom", fontsize=10, color="#222")
            xs.append(i * 3 + 0.5)
            names.append(NAMES.get(m, m).replace(" ", "\n", 1) + ("" if s == "default" else "\n(\"be careful\")"))
        ax.set_xticks(xs)
        ax.set_xticklabels(names, fontsize=11)
        ax.set_ylabel(label, fontsize=13)
        ax.set_ylim(0, 1.12)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        ax.tick_params(axis="y", labelsize=11)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.grid(axis="y", color="#e5e5e5", lw=0.8)
        ax.set_axisbelow(True)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, [f"{l} framing" for l in labels], loc="lower center", ncol=2, fontsize=12, frameon=False,
               bbox_to_anchor=(0.5, 0.0))
    n_eps = len(eps)
    per_cell = sorted({c["n"] for c in summary["cells"].values()})
    n_txt = f"{per_cell[0]}" if len(per_cell) == 1 else f"{per_cell[0]}–{per_cell[-1]}"
    fig.suptitle("Same code, framed as safety vs capabilities research\n"
                 f"one bar = mean over {n_txt} episodes, whiskers = 95% bootstrap CI", fontsize=13)
    fig.tight_layout(rect=(0, 0.06, 1, 0.92))
    fig.savefig(out / "completion_and_stopping.png", dpi=160)
    plt.close(fig)

    # per-task paired gaps: one dot = one (task) mean gap for one model
    fig, ax = plt.subplots(figsize=(10, 0.6 * sum(len(v) for v in summary["per_task"].values()) + 2))
    y = 0
    ticks, labels = [], []
    for key, tasks in summary["per_task"].items():
        for t, d in tasks.items():
            ax.plot([d["safety"], d["capabilities"]], [y, y], color="#999", lw=2, zorder=1)
            ax.scatter([d["capabilities"]], [y], color=COL["capabilities"], s=70, zorder=2)
            ax.scatter([d["safety"]], [y], color=COL["safety"], s=70, zorder=2)
            ticks.append(y)
            m_, s_ = key.split("|")
            labels.append(f"{NAMES.get(m_, m_)}{'' if s_ == 'default' else ' (careful)'} · {t} (n={d['n']})")
            y += 1
    ax.set_yticks(ticks)
    ax.set_yticklabels(labels, fontsize=11)
    lo_x = max(0.0, min(min(d["safety"], d["capabilities"]) for ts in summary["per_task"].values() for d in ts.values()) - 0.05)
    ax.set_xlim(lo_x, 1.0)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Hidden rubric items completed (mean over seeds; axis starts at %d%%)" % round(100 * lo_x), fontsize=13)
    ax.set_title("One dot = one task's mean completion under one framing\n(orange = safety framing, blue = capabilities framing)",
                 fontsize=13)
    ax.grid(axis="x", color="#e5e5e5", lw=0.8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "per_task.png", dpi=160)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", nargs="+", required=True)
    p.add_argument("--out", default=None)
    a = p.parse_args()
    out = Path(a.out) if a.out else RESULTS_DIR / "_".join(a.runs)
    out.mkdir(parents=True, exist_ok=True)
    eps = load_episodes(a.runs)
    from sfe.render import list_tasks, load_task
    task_meta = {t: load_task(t).meta for t in list_tasks()}
    summary = summarize(eps)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    (out / "episodes.json").write_text(json.dumps(eps, indent=1))
    write_markdown(summary, eps, out, task_meta)
    plot(summary, eps, out)
    print((out / "results.md").read_text())
    print(f"\nwrote {out}/results.md, summary.json, completion_and_stopping.png, per_task.png")


if __name__ == "__main__":
    main()
