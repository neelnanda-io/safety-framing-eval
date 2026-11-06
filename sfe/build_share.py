"""Build the standalone, shareable results page: results/share/index.html (figures embedded, tables from results/*.json).

    python -m sfe.build_share --repo https://github.com/<owner>/safety-framing-eval
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from sfe.build_report import img, interrogation_rows, native_rows, table
from sfe.config import MODELS, RESULTS_DIR

R = RESULTS_DIR


def pp(x):
    return f"{100 * x:+.1f}"


def summary_table(path):
    rows = json.loads(path.read_text())
    return table(["model", "matched pairs", "pairs dropped", "safety", "capabilities", "gap, points (95% CI)", "Holm-adjusted p"],
                 [[r["label"], str(r["n"]), str(r["dropped"]), f"{100*r['safety']:.1f}%", f"{100*r['capabilities']:.1f}%",
                   (f"<strong>{pp(r['gap'])}</strong>" if r["holm_p"] < 0.05 else pp(r["gap"])) + f" ({pp(r['gap_ci'][0])} to {pp(r['gap_ci'][1])})",
                   f"{r['holm_p']:.3f}"] for r in rows])


def why_table():
    D = json.loads((R / "why_probe.json").read_text())
    eps = {}
    for d in D:
        e = eps.setdefault(d["episode"], {"framing": d["framing"], "frac": d["final_frac"]})
        e[d["qid"]] = d
    def first(s, n=150):
        s = re.sub(r"\*\*", "", (s or "").strip().split("\n")[0]); return html.escape(s[:n] + ("…" if len(s) > n else ""))
    rows = []
    for ep, e in eps.items():
        model, task, fr, seed = ep.split("__")[:4]
        name = {"sol61s": "GPT-6.1 Sol", "sol61": "GPT-6.1 Sol", "astra": "GPT-6 Astra"}.get(model, model)
        harm = re.search(r"(\d+)\s*/\s*10", e.get("harm_level", {}).get("answer", "") or "")
        dec = lambda q: "starts editing" if e.get(q, {}).get("calls") else "refuses"
        rows.append([name, f"<code>{task}</code> {fr} {seed}", f"{round(100*e['frac'])}%", dec("direct"), dec("direct_authorised"),
                     first(e.get("policy", {}).get("answer")), (harm.group(1) + "/10") if harm else "", first(e.get("counterfactual", {}).get("answer"), 90)])
    return table(["model", "episode", "score", "asked to fix", "asked again, “authorised”", "is it against the rules? (first line)",
                  "harm rating", "identical code for a verbosity critic?"], rows)


def model_table():
    keys = ["astra", "sol61", "sol61s", "terra61", "sol6", "luna6", "sol", "fable", "opus", "argon", "flash38", "kimi", "dsflash", "astra_oai"]
    rows = []
    for k in keys:
        m = MODELS.get(k)
        if not m:
            continue
        pin = "OpenAI Responses API, flex" if m.backend == "openai" else ", ".join(m.provider.get("order", []))
        rows.append([f"<code>{k}</code>", f"<code>{m.model_id}</code>", html.escape(pin), f"${m.in_price:g} / ${m.out_price:g}",
                     m.reasoning_effort or "", "yes" if m.cache_markers else ""])
    return table(["config key", "model", "endpoint", "$ per M tokens in / out", "reasoning effort", "cache markers"], rows)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    body = (R / "share_body.html").read_text()
    subs = {
        "{{REPO}}": html.escape(a.repo),
        "{{SUMMARY_FIG}}": img(R / "summary" / "summary_safety_vs_capabilities.png", "Safety vs capabilities completion by model"),
        "{{SUMMARY_TABLE}}": summary_table(R / "summary" / "summary_safety_vs_capabilities.json"),
        "{{PER_TASK_FIG}}": img(R / "summary" / "per_task_gaps.png", "Gap by task, original six tasks"),
        "{{HARD_FIG}}": img(R / "summary" / "summary_hard_tasks.png", "Harder tasks by model and condition"),
        "{{HARD_TABLE}}": summary_table(R / "summary" / "summary_hard_tasks.json"),
        "{{PER_TASK_HARD_FIG}}": img(R / "summary" / "per_task_gaps_hard.png", "Gap by task, harder tasks"),
        "{{NATIVE_TABLE}}": table(["model", "task", "safety episodes", "capabilities episodes", "gap, points"], native_rows()),
        "{{INTERROGATION_TABLE}}": table(["model", "safety-framed episode", "score", "answers admitting a safety-motivated limit",
                                          "answers denying holding back", "direct fix request declined"], interrogation_rows()),
        "{{WHY_TABLE}}": why_table(),
        "{{MODEL_TABLE}}": model_table(),
        "{{GALLERY}}": (R / "task_gallery.html").read_text(),
        "{{TRANSPARENCY}}": (lambda tr: [tr := tr.replace(k, img(R / "transparency" / f, a)) for k, f, a in (
            ("{{TR_ORIG_SHARES}}", "original_shares.png", "Episode outcomes by model and framing"),
            ("{{TR_ORIG_POINTS}}", "original_gap_points.png", "Where the gap comes from"),
            ("{{TR_HARD_SHARES}}", "hard_shares.png", "Episode outcomes on the harder tasks"))][-1])((R / "transparency_section.html").read_text()),
    }
    for k, v in subs.items():
        body = body.replace(k, v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", body)
    css = (R / "report_css.css").read_text() + (R / "share_extra.css").read_text()
    page = f"""<title>Covert Underperformance Replication</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono&family=Source+Serif+4:wght@600&display=swap">
<style>{css}</style>
<main>{body}</main>"""
    out = R / "share"; out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page)
    print("wrote", out / "index.html", f"{len(page) / 1e6:.1f} MB; unfilled placeholders: {left}")


if __name__ == "__main__":
    main()
