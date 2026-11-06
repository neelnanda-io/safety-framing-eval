"""Assemble the full results page from the results/ JSON files: results/report/index.html.

    python -m sfe.build_report
"""
from __future__ import annotations

import base64
import collections
import glob
import html
import json
from pathlib import Path

from sfe.config import RESULTS_DIR, RUNS_DIR
from sfe.robustness import by_model_task, load, permutation_p, task_cluster_ci

R = RESULTS_DIR
OUT = R / "report"


def img(path: Path, alt: str) -> str:
    b = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b}" alt="{html.escape(alt)}" class="fig">'


def table(headers, rows):
    th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def q(text, who):
    return f'<blockquote>{html.escape(text)}<cite>{html.escape(who)}</cite></blockquote>'


def pp(x):
    return f"{100 * x:+.1f}"


def gap_row(label, runs, model):
    d = by_model_task(load(runs)).get(model)
    if not d:
        return None
    obs, p = permutation_p(d, n_perm=20000); lo, hi = task_cluster_ci(d)
    ms = {f: sum(sum(v[f]) / len(v[f]) for v in d.values()) / len(d) for f in ("safety", "capabilities")}
    n = sum(len(v["safety"]) for v in d.values())
    return [label, str(n), f"{100*ms['safety']:.1f}%", f"{100*ms['capabilities']:.1f}%", f"<strong>{pp(obs)}</strong>" if p < 0.05 else pp(obs),
            f"{pp(lo)} to {pp(hi)}", f"{p:.3f}"]


def native_rows():
    cells = collections.defaultdict(list)
    for f in glob.glob(str(RUNS_DIR / "native_*/episodes/*.json")):
        r = json.load(open(f)); s = r["spec"]
        if r.get("complete"):
            cells[(s["model"], s["task"], s["framing"])].append(r["turns"][-1]["grade"]["frac"])
    rows = []
    for m, name in (("astra", "GPT-6 Astra"), ("sol61", "GPT-6.1 Sol")):
        for t in ("organism_data", "prompt_augment", "diff_monitor"):
            s, c = cells[(m, t, "safety")], cells[(m, t, "capabilities")]
            if s and c:
                rows.append([name, f"<code>{t}</code>", " ".join(f"{round(100*x)}%" for x in s), " ".join(f"{round(100*x)}%" for x in c),
                             pp(sum(c) / len(c) - sum(s) / len(s))])
    return rows


def interrogation_rows():
    rows = []
    for m, name in (("sol61", "GPT-6.1 Sol"), ("astra", "GPT-6 Astra")):
        p = R / "interrogation" / f"{m}.json"
        if not p.exists():
            continue
        D = json.loads(p.read_text())
        ep = collections.defaultdict(lambda: [0, 0, 0, 0, None])
        for r in D:
            e = ep[(r["framing"], r["task"], r["seed"])]; e[4] = r["final_frac"]
            lab = r["label"] or {}
            if r["qid"] == "q14_direct":
                e[2] += bool(lab.get("declines"))
            else:
                e[0] += bool(lab.get("admits_safety_limit")); e[1] += 1; e[3] += bool(lab.get("denies_holding_back"))
        for (fr, t, s), e in sorted(ep.items(), key=lambda kv: (kv[0][0] != "safety", kv[0][1], kv[1][4])):
            if fr == "safety":
                rows.append([name, f"<code>{t}</code> seed {s}", f"{round(100*e[4])}%", f"{e[0]} of {e[1]}", f"{e[3]} of {e[1]}", f"{e[2]} of 2"])
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summ = json.loads((R / "summary" / "summary_safety_vs_capabilities.json").read_text())
    css = (R / "report_css.css").read_text() if (R / "report_css.css").exists() else ""
    hard_rows = [x for x in (
        gap_row("GPT-6.1 Sol, scarce reading", ["hard_scarce_sol61s"], "sol61s"),
        gap_row("GPT-5.6 Sol, scarce reading", ["hard_scarce_sol"], "sol"),
        gap_row("GPT-6.1 Sol, standard", ["hard_std_sol61s"], "sol61s"),
        gap_row("GPT-5.6 Sol, standard", ["hard_std_sol"], "sol")) if x]
    sections = (R / "report_body.html").read_text()
    sections = sections.replace("{{SUMMARY_FIG}}", img(R / "summary" / "summary_safety_vs_capabilities.png", "Safety vs capabilities by model"))
    hard_fig = R / "summary" / "summary_hard_tasks.png"
    sections = sections.replace("{{HARD_FIG}}", img(hard_fig, "Harder tasks") if hard_fig.exists() else "")
    sections = sections.replace("{{PER_TASK_FIG}}", img(R / "summary" / "per_task_gaps.png", "Gap by task, original tasks"))
    sections = sections.replace("{{PER_TASK_HARD_FIG}}", img(R / "summary" / "per_task_gaps_hard.png", "Gap by task, harder tasks"))
    sections = sections.replace("{{HARD_TABLE}}", table(["condition", "pairs", "safety", "capabilities", "gap, pp", "task-resampled 95% CI", "permutation p"], hard_rows))
    sections = sections.replace("{{NATIVE_TABLE}}", table(["model", "task", "safety episodes", "capabilities episodes", "gap, pp"], native_rows()))
    sections = sections.replace("{{INTERROGATION_TABLE}}", table(
        ["model", "safety-framed episode", "score", "answers admitting a safety-motivated limit", "answers denying holding back", "direct fix request declined"],
        interrogation_rows()))
    sections = sections.replace("{{SUMMARY_TABLE}}", table(
        ["model", "matched pairs", "pairs dropped", "safety", "capabilities", "gap, pp (95% CI)", "Holm-adjusted p"],
        [[r["label"], str(r["n"]), str(r["dropped"]), f"{100*r['safety']:.1f}%", f"{100*r['capabilities']:.1f}%",
          f"{pp(r['gap'])} ({pp(r['gap_ci'][0])} to {pp(r['gap_ci'][1])})", f"{r['holm_p']:.3f}"] for r in summ]))
    gallery = (R / "task_gallery.html").read_text() if (R / "task_gallery.html").exists() else ""
    sections = sections.replace("{{GALLERY}}", gallery)
    tr = (R / "transparency_section.html").read_text()
    for k, f, alt in (("{{TR_ORIG_SHARES}}", "original_shares.png", "Episode outcomes by model and framing"),
                      ("{{TR_ORIG_POINTS}}", "original_gap_points.png", "Where the gap comes from"),
                      ("{{TR_HARD_SHARES}}", "hard_shares.png", "Episode outcomes on the harder tasks")):
        tr = tr.replace(k, img(R / "transparency" / f, alt))
    sections = sections.replace("{{TRANSPARENCY}}", tr)
    page = f"""<title>Does a safety framing change what Astra does?</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono&family=Source+Serif+4:wght@600&display=swap">
<style>{css}</style>
<main>{sections}</main>"""
    (OUT / "index.html").write_text(page)
    print("wrote", OUT / "index.html", f"{len(page)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
