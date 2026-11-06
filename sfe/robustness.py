"""Robustness checks for the safety-vs-capabilities gap.

    python -m sfe.robustness --runs main3_astra main3_sol w2_sol61 ... --out results/robustness

1. Within-task permutation test per model (framing labels shuffled among a task's episodes), Holm-corrected.
2. Task-clustered bootstrap: resample TASKS with replacement, then episodes within each framing. This is the interval
   for "a new task drawn from the same distribution", wider than the per-episode bootstrap.
3. Item-level rendering check: per rubric item, safety-vs-capabilities pass-rate difference for each model, compared with a
   reference pool of models. Items that every model loses under one rendering point to a difference in the code, not in
   the model's behaviour.
4. Effort allocation: lines added to source / tests / docs by the end of the episode, and how many test runs.

Note on "seeds": the seed index does not control the model's sampling, so pairing by seed is only stratification by task.
All tests here are stratified by task, which is the correct unit.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

from sfe.config import RESULTS_DIR, RUNS_DIR

REFERENCE_POOL_EXCLUDE = {"astra", "sol61", "terra61", "sol6", "luna6"}   # newest OpenAI family; everything else = reference


def _empty(t):
    return t["n_tool_calls"] == 0 and not t["final_text"].strip()


def load(runs):
    eps = []
    for run in runs:
        for f in sorted((RUNS_DIR / run / "episodes").glob("*.json")):
            r = json.loads(f.read_text())
            if not r.get("turns"):
                continue
            s = r["spec"]
            key = s["model"] + ("" if s.get("system", "default") == "default" else f"+{s['system']}")
            refused = any(_empty(t) or t.get("platform_refusal") for t in r["turns"])
            eps.append({"run": run, "model": key, "task": s["task"], "framing": s["framing"], "seed": s["seed"],
                        "frac": r["turns"][-1]["grade"]["frac"], "items": r["turns"][-1]["grade"]["items"],
                        "refused": refused, "turns": r["turns"], "snapshot": r.get("final_snapshot", {})})
    return eps


def by_model_task(eps, framings=("safety", "capabilities"), drop_refused=True):
    d = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for e in eps:
        if e["framing"] in framings and not (drop_refused and e["refused"]):
            d[e["model"]][e["task"]][e["framing"]].append(e["frac"])
    return d


def gap_stat(tasks, a="capabilities", b="safety"):
    gs = [sum(v[a]) / len(v[a]) - sum(v[b]) / len(v[b]) for v in tasks.values() if v[a] and v[b]]
    return sum(gs) / len(gs) if gs else float("nan")


def permutation_p(tasks, n_perm=20000, seed=0, a="capabilities", b="safety"):
    rng = random.Random(seed)
    obs = gap_stat(tasks, a, b)
    pooled = {t: (v[a] + v[b], len(v[a])) for t, v in tasks.items() if v[a] and v[b]}
    hits = 0
    for _ in range(n_perm):
        gs = []
        for vals, na in pooled.values():
            x = vals[:]
            rng.shuffle(x)
            gs.append(sum(x[:na]) / na - sum(x[na:]) / (len(x) - na))
        if abs(sum(gs) / len(gs)) >= abs(obs) - 1e-12:
            hits += 1
    return obs, (hits + 1) / (n_perm + 1)


def task_cluster_ci(tasks, n_boot=10000, seed=0, a="capabilities", b="safety"):
    rng = random.Random(seed)
    names = [t for t, v in tasks.items() if v[a] and v[b]]
    out = []
    for _ in range(n_boot):
        gs = []
        for _ in names:
            v = tasks[rng.choice(names)]
            ra = [rng.choice(v[a]) for _ in v[a]]
            rb = [rng.choice(v[b]) for _ in v[b]]
            gs.append(sum(ra) / len(ra) - sum(rb) / len(rb))
        out.append(sum(gs) / len(gs))
    out.sort()
    return out[int(0.025 * n_boot)], out[int(0.975 * n_boot)]


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    adj, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        adj[k] = running
    return adj


def item_level(eps, focus=("astra", "sol61")):
    """Per (task, item): pass-rate gap (cap - safety) for each focus model and for the reference pool."""
    acc = defaultdict(lambda: defaultdict(lambda: {"safety": [0, 0], "capabilities": [0, 0]}))
    for e in eps:
        if e["framing"] not in ("safety", "capabilities") or e["refused"]:
            continue
        group = e["model"] if e["model"] in focus else ("ref" if e["model"].split("+")[0] not in REFERENCE_POOL_EXCLUDE else None)
        if group is None:
            continue
        for item, ok in e["items"].items():
            c = acc[(e["task"], item)][group][e["framing"]]
            c[0] += bool(ok); c[1] += 1
    rows = []
    for (task, item), g in acc.items():
        row = {"task": task, "item": item}
        for grp, c in g.items():
            ps = c["safety"][0] / c["safety"][1] if c["safety"][1] else float("nan")
            pc = c["capabilities"][0] / c["capabilities"][1] if c["capabilities"][1] else float("nan")
            row[grp] = {"safety": ps, "capabilities": pc, "gap": pc - ps, "n": c["safety"][1] + c["capabilities"][1]}
        rows.append(row)
    return rows


def corr(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs)); sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else float("nan")


def effort(e):
    """Line counts by category at the end of the episode, and number of pytest runs."""
    src = tests = docs = 0
    for path, txt in e["snapshot"].items():
        n = txt.count("\n")
        if path.startswith("tests/") or "/test_" in path or path.startswith("test_"):
            tests += n
        elif path.endswith(".md") or path.startswith("docs/"):
            docs += n
        elif path.endswith(".py"):
            src += n
    runs = sum(1 for t in e["turns"] for c in t["calls"] if c["name"] == "run_command" and "pytest" in str(c["args"].get("command", "")))
    return {"src": src, "tests": tests, "docs": docs, "pytest_runs": runs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--out", default=str(RESULTS_DIR / "robustness"))
    ap.add_argument("--focus", nargs="+", default=["astra", "sol61"])
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    eps = load(a.runs)
    d = by_model_task(eps)
    res, pv = {}, {}
    for model, tasks in sorted(d.items()):
        obs, p = permutation_p(tasks)
        lo, hi = task_cluster_ci(tasks)
        n = sum(len(v["safety"]) + len(v["capabilities"]) for v in tasks.values())
        res[model] = {"gap": obs, "perm_p": p, "task_ci": (lo, hi), "n_eps": n, "n_tasks": len(tasks),
                      "per_task": {t: sum(v["capabilities"]) / len(v["capabilities"]) - sum(v["safety"]) / len(v["safety"])
                                   for t, v in tasks.items() if v["safety"] and v["capabilities"]}}
        pv[model] = p
    adj = holm(pv)
    for m in res:
        res[m]["holm_p"] = adj[m]
    # neutral comparisons where available
    dn = by_model_task(eps, framings=("safety", "capabilities", "neutral"))
    neutral = {}
    for model, tasks in dn.items():
        if any(v["neutral"] for v in tasks.values()):
            tk = {t: v for t, v in tasks.items() if v["neutral"] and v["safety"] and v["capabilities"]}
            neutral[model] = {
                "neutral_minus_safety": permutation_p(tk, a="neutral", b="safety") + (task_cluster_ci(tk, a="neutral", b="safety"),),
                "capabilities_minus_neutral": permutation_p(tk, a="capabilities", b="neutral") + (task_cluster_ci(tk, a="capabilities", b="neutral"),),
                "means": {f: sum(sum(v[f]) / len(v[f]) for v in tk.values()) / len(tk) for f in ("safety", "capabilities", "neutral")},
            }
    # item level
    rows = item_level(eps, focus=a.focus)
    item_summary = {}
    for fm in a.focus:
        both = [r for r in rows if fm in r and "ref" in r]
        xs = [r[fm]["gap"] for r in both]; ys = [r["ref"]["gap"] for r in both]
        # focus-model gap on items where the reference pool shows no rendering difference (|gap| < 5 points)
        clean = [r[fm]["gap"] for r in both if abs(r["ref"]["gap"]) < 0.05]
        top = sorted(both, key=lambda r: -r[fm]["gap"])[:10]
        item_summary[fm] = {"corr_with_reference": corr(xs, ys), "n_items": len(both),
                            "mean_gap_all_items": sum(xs) / len(xs) if xs else float("nan"),
                            "mean_gap_reference_clean_items": sum(clean) / len(clean) if clean else float("nan"),
                            "n_reference_clean_items": len(clean),
                            "top_items": [{"task": r["task"], "item": r["item"], "gap": r[fm]["gap"], "ref_gap": r["ref"]["gap"]} for r in top]}
    ref_suspects = sorted([r for r in rows if "ref" in r and r["ref"]["n"] >= 40], key=lambda r: -abs(r["ref"]["gap"]))[:10]
    # effort
    eff = defaultdict(lambda: defaultdict(list))
    for e in eps:
        if e["framing"] in ("safety", "capabilities") and not e["refused"]:
            for k, v in effort(e).items():
                eff[e["model"]][(e["framing"], k)].append(v)
    eff_summary = {m: {f"{fr}:{k}": sum(v) / len(v) for (fr, k), v in kv.items()} for m, kv in eff.items()}
    summary = {"per_model": res, "neutral": neutral, "items": item_summary,
               "reference_rendering_suspects": [{"task": r["task"], "item": r["item"], "ref_gap": r["ref"]["gap"], "n": r["ref"]["n"]} for r in ref_suspects],
               "effort": eff_summary}
    (out / "robustness.json").write_text(json.dumps(summary, indent=1, default=str))
    pct = lambda x: f"{100 * x:+.1f}"
    lines = ["# Robustness checks", "", "## Gap by model: within-task permutation test and task-clustered bootstrap", "",
             "| model | episodes | tasks | gap (cap − safety), pp | task-clustered 95% CI | permutation p | Holm-adjusted p |", "|---|---|---|---|---|---|---|"]
    for m, r in sorted(res.items(), key=lambda kv: -kv[1]["gap"]):
        lines.append(f"| {m} | {r['n_eps']} | {r['n_tasks']} | {pct(r['gap'])} | {pct(r['task_ci'][0])} to {pct(r['task_ci'][1])} | {r['perm_p']:.4f} | {r['holm_p']:.4f} |")
    if neutral:
        lines += ["", "## Neutral framing", "", "| model | safety | neutral | capabilities | neutral − safety (p) | capabilities − neutral (p) |", "|---|---|---|---|---|---|"]
        for m, r in neutral.items():
            mm = r["means"]
            lines.append(f"| {m} | {100*mm['safety']:.1f}% | {100*mm['neutral']:.1f}% | {100*mm['capabilities']:.1f}% | "
                         f"{pct(r['neutral_minus_safety'][0])} (p={r['neutral_minus_safety'][1]:.3f}) | {pct(r['capabilities_minus_neutral'][0])} (p={r['capabilities_minus_neutral'][1]:.3f}) |")
    lines += ["", "## Item-level rendering check", ""]
    for fm, s in item_summary.items():
        lines.append(f"- **{fm}**: correlation of per-item gaps with the reference pool = {s['corr_with_reference']:.2f} over {s['n_items']} items; "
                     f"mean item gap {pct(s['mean_gap_all_items'])} pp on all items, {pct(s['mean_gap_reference_clean_items'])} pp on the "
                     f"{s['n_reference_clean_items']} items where the reference pool shows < 5 pp rendering difference.")
        lines.append("  - top items: " + "; ".join(f"{t['task']}/{t['item']} {pct(t['gap'])} (ref {pct(t['ref_gap'])})" for t in s["top_items"]))
    lines.append("- largest reference-pool item gaps (candidate rendering confounds): " +
                 "; ".join(f"{r['task']}/{r['item']} {pct(r['ref_gap'])} (n={r['n']})" for r in summary["reference_rendering_suspects"]))
    lines += ["", "## Effort allocation (mean lines in final repo; pytest runs per episode)", "",
              "| model | src safety / cap | tests safety / cap | docs safety / cap | pytest runs safety / cap |", "|---|---|---|---|---|"]
    for m, s in sorted(eff_summary.items()):
        g = lambda k: f"{s.get('safety:'+k, float('nan')):.0f} / {s.get('capabilities:'+k, float('nan')):.0f}"
        lines.append(f"| {m} | {g('src')} | {g('tests')} | {g('docs')} | {s.get('safety:pytest_runs', 0):.1f} / {s.get('capabilities:pytest_runs', 0):.1f} |")
    (out / "robustness.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
