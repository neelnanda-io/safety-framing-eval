"""Recompute the toy-task numbers touched by the shared temporary folder on the laptop, and check them against the saved
result files. Background: docs/NOTES.md, section "Episodes that ran at the same time on the laptop shared a temporary
folder".

    python3 scripts/shared_tmp_numbers.py sensitivity  # results/real/shared_tmp_sensitivity.json, point 4: the published
                                                       # numbers with each set of affected episodes dropped (sets in
                                                       # results/real/shared_tmp_drop_sets.json)
    python3 scripts/shared_tmp_numbers.py reruns       # results/real/shared_tmp_reruns.json, "table": the harder-task
                                                       # numbers as published / with the sixteen spoiled episodes and their
                                                       # twins dropped / with each spoiled episode replaced by its re-run
    python3 scripts/shared_tmp_numbers.py seeds        # the same file, "permutation_seed_check": Holm p over the
                                                       # permutation test's seeds 0-9 (slow: about ten minutes)
    python3 scripts/shared_tmp_numbers.py per-task     # gap per harder task in the three versions (printed only)
    python3 scripts/shared_tmp_numbers.py all          # the first two and per-task (add --seeds for the slow check)

Needs the episode data: the data release unpacked at the repository root, which gives runs/ and, for the re-runs,
runs_rerun/ (the `reruns` and `seeds` commands need those sixteen files). Run from the repository root with SFE_RUNS_DIR unset. Nothing is written; the exit
code is 1 if any recomputed number differs from the saved file.

The numbers are the project's own: sfe.summary_plot's groups, flagged() and boot(), and sfe.robustness's permutation_p()
and holm(), exactly as `python3 -m sfe.summary_plot [--hard]` uses them for the published tables. load_group() is copied
below with two optional changes (a set of episodes to drop, and a map from an original episode file to its re-run), and the
copy is checked to return what sfe.summary_plot.load_group returns when neither is used.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfe.config import RUNS_DIR  # noqa: E402
from sfe.robustness import holm, permutation_p  # noqa: E402
from sfe.summary_plot import FRAME, GROUPS, GROUPS_HARD, boot, flagged, load_group  # noqa: E402

RERUN_DIR = ROOT / "runs_rerun"
SENS = ROOT / "results" / "real" / "shared_tmp_sensitivity.json"
DROPS = ROOT / "results" / "real" / "shared_tmp_drop_sets.json"
RERUNS = ROOT / "results" / "real" / "shared_tmp_reruns.json"


def load_group_x(model, system, runs, exclude=frozenset(), replace=None, keep_flagged=False):
    """sfe.summary_plot.load_group with two options. `exclude`: episode files ("runs/<run>/episodes/<file>"); a pair is
    dropped when either twin is in it. `replace`: episode file -> path of the file to read instead. `keep_flagged`: keep
    the pairs that load_group drops as refused or blocked (the "over all episodes" figures)."""
    replace = replace or {}
    eps = {}
    for run in runs:
        for f in (RUNS_DIR / run / "episodes").glob("*.json"):
            rel = f"runs/{run}/episodes/{f.name}"
            r = json.loads(Path(replace.get(rel, f)).read_text())
            s = r["spec"]
            if s["model"] != model or s.get("system", "default") != system or s["framing"] not in FRAME or not r.get("turns"):
                continue
            eps[(run, s["task"], s["seed"], s["framing"])] = (r["turns"][-1]["grade"]["frac"], flagged(r), rel)
    pairs, dropped, dropped_for_exclusion = [], 0, 0
    for (run, task, seed, fr), (v, bad, rel) in eps.items():
        if fr != "safety":
            continue
        tw = eps.get((run, task, seed, "capabilities"))
        if tw is None:
            continue
        if (bad or tw[1]) and not keep_flagged:
            dropped += 1
            continue
        if rel in exclude or tw[2] in exclude:
            dropped_for_exclusion += 1
            continue
        pairs.append((task, v, tw[0]))
    return pairs, dropped, dropped_for_exclusion


def stats(pairs, seed=0):
    s = [p[1] for p in pairs]
    c = [p[2] for p in pairs]
    g = [p[2] - p[1] for p in pairs]
    tasks = defaultdict(lambda: defaultdict(list))
    for t, sv, cv in pairs:
        tasks[t]["safety"].append(sv)
        tasks[t]["capabilities"].append(cv)
    _, p = permutation_p(tasks, n_perm=20000, seed=seed)
    return {"n": len(pairs), "safety": sum(s) / len(s), "capabilities": sum(c) / len(c), "gap": sum(g) / len(g),
            "gap_ci": boot(g), "p": p}


def table(groups, exclude=frozenset(), replace=None, keep_flagged=False):
    """One table as sfe.summary_plot builds it: a row per group, Holm-corrected within the table."""
    rows, pv = [], {}
    for label, model, system, runs, _company in groups:
        pairs, dropped, _ = load_group_x(model, system, runs, exclude, replace, keep_flagged)
        if not pairs:
            continue
        st = stats(pairs)
        st.update(label=label, dropped=dropped, pairs=pairs)
        rows.append(st)
        pv[label] = st["p"]
    adj = holm(pv)
    for r in rows:
        r["holm_p"] = adj[r["label"]]
    return rows


def fmt(r, with_holm=True):
    """A row rounded the way the result files store it."""
    return {"pairs": r["n"], "safety": round(100 * r["safety"], 1), "capabilities": round(100 * r["capabilities"], 1),
            "gap": round(100 * r["gap"], 1), "gap_95ci": [round(100 * x, 1) for x in r["gap_ci"]], "p": round(r["p"], 4),
            "holm_p": round(r["holm_p"], 4) if with_holm else None}


def check_identity():
    for label, model, system, runs, _company in GROUPS + GROUPS_HARD:
        a, da = load_group(model, system, runs)
        b, db, _ = load_group_x(model, system, runs)
        assert sorted(a) == sorted(b) and da == db, f"copied loader differs from sfe.summary_plot.load_group on {label}"


def show(name, rows):
    print(f"\n{name}")
    print(f"  {'group':32} {'pairs':>5} {'safety':>7} {'capab.':>7} {'gap':>6}  {'95% interval':>15} {'p':>7} {'Holm p':>7}")
    for r in rows:
        f = fmt(r)
        print(f"  {r['label']:32} {f['pairs']:5d} {f['safety']:7.1f} {f['capabilities']:7.1f} {f['gap']:+6.1f}  "
              f"{f['gap_95ci'][0]:+6.1f} to {f['gap_95ci'][1]:+5.1f} {f['p']:7.4f} {f['holm_p']:7.4f}")


def cmd_sensitivity() -> int:
    """results/real/shared_tmp_sensitivity.json, point4_sensitivity: key_rows (every field) and other_rows_that_move."""
    saved = json.loads(SENS.read_text())["point4_sensitivity"]
    sets = json.loads(DROPS.read_text())["sets"]
    versions = ["(a) as published"] + list(sets)
    bad = 0
    for v in versions:
        ex = frozenset(sets.get(v, []))
        tabs = {"original_six": table(GROUPS, ex), "hard": table(GROUPS_HARD, ex),
                "hard_all_episodes_astra": table(GROUPS_HARD[:2], ex, keep_flagged=True)}
        print(f"\n=== {v}")
        for part, rows in tabs.items():
            for r in rows:
                key = f"{part} | {r['label']}"
                mine = fmt(r, with_holm=part != "hard_all_episodes_astra")
                if key in saved["key_rows"]:
                    want = saved["key_rows"][key][v]
                    ok = mine == want
                    bad += not ok
                    print(f"  {'ok  ' if ok else 'DIFF'} {key:52} gap {mine['gap']:+5.1f}  pairs {mine['pairs']:3d}  "
                          f"p {mine['p']:.4f}  Holm {mine['holm_p'] if mine['holm_p'] is not None else '-'}"
                          + ("" if ok else f"   saved: {want}"))
                elif key in saved["other_rows_that_move"]:
                    want = saved["other_rows_that_move"][key][v]
                    ok = mine["gap"] == want
                    bad += not ok
                    print(f"  {'ok  ' if ok else 'DIFF'} {key:52} gap {mine['gap']:+5.1f}" + ("" if ok else f"   saved: {want}"))
    print(f"\nsensitivity: {'every saved number reproduced' if not bad else f'{bad} rows differ'}")
    return 1 if bad else 0


def rerun_maps():
    sixteen = json.loads(RERUNS.read_text())["sixteen"]
    exclude = frozenset(e["original"] for e in sixteen)
    replace, missing = {}, []
    for e in sixteen:
        p = ROOT / e["rerun"]
        if p.exists() and json.loads(p.read_text()).get("complete"):
            replace[e["original"]] = p
        else:
            missing.append(e["rerun"])
    if missing:
        raise SystemExit(f"re-run files missing or incomplete (unpack the data release): {missing}")
    return exclude, replace


def three_versions():
    exclude, replace = rerun_maps()
    return {"published": {"hard": table(GROUPS_HARD), "all_astra": table(GROUPS_HARD[:2], keep_flagged=True)},
            "dropped": {"hard": table(GROUPS_HARD, exclude=exclude),
                        "all_astra": table(GROUPS_HARD[:2], exclude=exclude, keep_flagged=True)},
            "replaced": {"hard": table(GROUPS_HARD, replace=replace),
                         "all_astra": table(GROUPS_HARD[:2], replace=replace, keep_flagged=True)}}


def cmd_reruns(versions=None) -> int:
    """results/real/shared_tmp_reruns.json, "table": every row and field of the three versions."""
    saved = json.loads(RERUNS.read_text())["table"]
    versions = versions or three_versions()
    bad = 0
    for ver, parts in versions.items():
        for part, rows in parts.items():
            want = {r["label"]: r for r in saved[ver][part]}
            for r in rows:
                mine = dict(label=r["label"], flagged_pairs_dropped=r["dropped"], **fmt(r, with_holm=part == "hard"))
                w = {k: want[r["label"]][k] for k in mine}
                if mine != w:
                    bad += 1
                    print(f"  DIFF {ver} {part} {r['label']}: {mine} saved {w}")
        show(f"{ver}, harder tasks, matched pairs", parts["hard"][:6])
        show(f"{ver}, GPT-6 Astra over all episodes (Holm p not used)", parts["all_astra"])
    print(f"\nre-runs: {'every saved row reproduced (all 11 harder-task rows and 2 Astra rows, three versions)' if not bad else f'{bad} rows differ'}")
    return 1 if bad else 0


def cmd_per_task(versions=None) -> int:
    """Gap per task (capabilities minus safety, points) for the rows that move, in each version."""
    versions = versions or three_versions()
    print("\nGap per harder task, points (mean over the pairs of that task; pairs in brackets)")
    for part, labels in (("hard", ["GPT-6 Astra, standard", "GPT-6 Astra, scarce reading", "GPT-6.1 Sol, standard",
                                   "GPT-6.1 Terra, standard"]), ("all_astra", ["GPT-6 Astra, standard"])):
        for label in labels:
            for ver in versions:
                r = next(x for x in versions[ver][part] if x["label"] == label)
                by = defaultdict(list)
                for t, sv, cv in r["pairs"]:
                    by[t].append(cv - sv)
                total = sum(sum(v) for v in by.values())
                cells = "  ".join(f"{t} {100 * sum(v) / len(v):+5.1f} ({len(v)})" for t, v in sorted(by.items()))
                share = 100 * sum(by.get("monitor_evasion_rl", [])) / total if total else float("nan")
                print(f"  {('over all episodes: ' if part == 'all_astra' else '') + label:42} {ver:9} {cells}"
                      f"   monitor_evasion_rl share of the summed gap: {share:.0f}%")
    return 0


def cmd_seeds() -> int:
    """results/real/shared_tmp_reruns.json, "permutation_seed_check": Holm p over permutation seeds 0-9."""
    saved = json.loads(RERUNS.read_text())["permutation_seed_check"]
    _, replace = rerun_maps()
    res = defaultdict(list)
    for ver, rep in (("published", None), ("replaced", replace)):
        groups = []
        for label, model, system, runs, _company in GROUPS_HARD:
            pairs, _, _ = load_group_x(model, system, runs, replace=rep)
            tasks = defaultdict(lambda: defaultdict(list))
            for t, sv, cv in pairs:
                tasks[t]["safety"].append(sv)
                tasks[t]["capabilities"].append(cv)
            groups.append((label, tasks))
        for seed in range(10):
            pv = {label: permutation_p(tasks, n_perm=20000, seed=seed)[1] for label, tasks in groups}
            adj = holm(pv)
            for lab in ("GPT-6.1 Sol, standard", "GPT-6.1 Terra, standard"):
                res[(ver, lab)].append((round(pv[lab], 4), round(adj[lab], 4)))
    bad = 0
    for (ver, lab), v in res.items():
        raw, hs = [p for p, _ in v], [h for _, h in v]
        name = f"{ver} {lab.replace(', standard', ' standard')}"
        text = f"Holm {min(hs)}-{max(hs)}, below 0.05 in {sum(h < 0.05 for h in hs)} of 10"
        if ver == "replaced":
            text = f"raw p {min(raw)}-{max(raw)}, " + text
        ok = saved.get(name) == text
        bad += not ok
        print(f"  {'ok  ' if ok else 'DIFF'} {name}: {text}" + ("" if ok else f"   saved: {saved.get(name)}"))
    print(f"\nseeds: {'reproduced' if not bad else f'{bad} lines differ'}")
    return 1 if bad else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["sensitivity", "reruns", "seeds", "per-task", "all"])
    ap.add_argument("--seeds", action="store_true", help="with `all`: also run the slow seed check")
    a = ap.parse_args()
    if os.environ.get("SFE_RUNS_DIR"):
        raise SystemExit("unset SFE_RUNS_DIR: the published numbers are read from runs/")
    if not (RUNS_DIR / "hard_std_astra" / "episodes").is_dir():
        raise SystemExit("runs/ is missing: unpack the data release at the repository root first")
    check_identity()
    print("copied loader returns exactly what sfe.summary_plot.load_group returns, on all 24 groups")
    code = 0
    if a.what in ("sensitivity", "all"):
        code |= cmd_sensitivity()
    if a.what in ("reruns", "per-task", "all"):
        versions = three_versions()
        if a.what in ("reruns", "all"):
            code |= cmd_reruns(versions)
        cmd_per_task(versions)
    if a.what == "seeds" or (a.what == "all" and a.seeds):
        code |= cmd_seeds()
    sys.exit(code)


if __name__ == "__main__":
    main()
