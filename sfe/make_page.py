"""Build a self-contained HTML results page from an analysis directory (summary.json, episodes.json, results.md).

    python -m sfe.make_page results/main_astra_main_sol --title "Safety-framing eval: Astra"
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

COL = {"capabilities": ("#2a78d6", "#3987e5"), "safety": ("#eb6834", "#d95926")}
MODEL_NAMES = {'astra': 'GPT-6 Astra', 'sol': 'GPT-5.6 Sol', 'sol61': 'GPT-6.1 Sol', 'argon': 'Gemini 4 Argon', 'flash38': 'Gemini 3.8 Flash', 'opus': 'Claude Opus 5.5', 'fable': 'Claude Fable 5.1', 'kimi': 'Kimi K3', 'dsflash': 'DeepSeek V4.1 Flash', 'flash': 'Gemini 3 Flash', 'terra61': 'GPT-6.1 Terra', 'sol6': 'GPT-6 Sol', 'luna6': 'GPT-6 Luna', 'sol61h': 'GPT-6.1 Sol', 'sol61s': 'GPT-6.1 Sol', 'astra_oai': 'GPT-6 Astra'}
MODEL_ORDER = ['astra', 'sol61', 'sol61s', 'terra61', 'sol6', 'luna6', 'sol', 'fable', 'opus', 'argon', 'flash38', 'kimi', 'dsflash']


def pct(x) -> str:
    return "n/a" if x is None or x != x else f"{100 * x:.0f}%"


def pct1(x) -> str:
    return "n/a" if x is None or x != x else f"{100 * x:.1f}%"


def bar_chart(cells: dict, metric: str, ci_key: str, title: str, models: list[tuple[str, str]], ymax: float = 1.0) -> str:
    """Grouped bars (capabilities, safety) per model with CI whiskers, as inline SVG with hover tooltips."""
    W, H = max(520, 70 * 2 * len(models) + 80), 300
    L, R, T, B = 56, 12, 36, 56
    pw, ph = W - L - R, H - T - B
    n = len(models)
    gw = pw / max(1, n)
    bw = min(56, gw * 0.32)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}" class="chart">']
    out.append(f'<text x="{L}" y="18" class="ctitle">{html.escape(title)}</text>')
    for k in range(0, 5):
        y = T + ph - ph * (k / 4) * (1 / ymax) if ymax else T
        if k / 4 > ymax:
            continue
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{L - 8}" y="{y + 4:.1f}" class="tick" text-anchor="end">{int(k * 25)}%</text>')
    for i, (m, s) in enumerate(models):
        cx = L + gw * (i + 0.5)
        label = MODEL_NAMES.get(m, m) + ("" if s == "default" else f" ({s})")
        out.append(f'<text x="{cx:.1f}" y="{H - B + 22}" class="xlab" text-anchor="middle">{html.escape(label)}</text>')
        for j, fr in enumerate(("capabilities", "safety")):
            c = cells.get(f"{m}|{s}|{fr}")
            if not c:
                continue
            v = c[metric]
            lo, hi = c[ci_key]
            x = cx - bw - 3 + j * (bw + 6)
            y = T + ph - ph * v / ymax
            h = ph * v / ymax
            ylo, yhi = T + ph - ph * lo / ymax, T + ph - ph * hi / ymax
            tip = f"{label} · {fr}: {pct1(v)} (95% CI {pct1(lo)}–{pct1(hi)}, n={c['n']})"
            out.append(f'<g class="bar bar-{fr}"><title>{html.escape(tip)}</title>'
                       f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(0.5, h):.1f}" rx="3"/>'
                       f'<line x1="{x + bw / 2:.1f}" x2="{x + bw / 2:.1f}" y1="{yhi:.1f}" y2="{ylo:.1f}" class="whisk"/>'
                       f'<line x1="{x + bw / 2 - 5:.1f}" x2="{x + bw / 2 + 5:.1f}" y1="{yhi:.1f}" y2="{yhi:.1f}" class="whisk"/>'
                       f'<line x1="{x + bw / 2 - 5:.1f}" x2="{x + bw / 2 + 5:.1f}" y1="{ylo:.1f}" y2="{ylo:.1f}" class="whisk"/>'
                       f'<text x="{x + bw / 2:.1f}" y="{min(y, yhi) - 6:.1f}" class="val" text-anchor="middle">{pct(v)}</text></g>')
    out.append("</svg>")
    return "\n".join(out)


def table(headers: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def build(res_dir: Path, title: str, intro_html: str, notes_html: str, examples: list[dict]) -> str:
    summary = json.loads((res_dir / "summary.json").read_text())
    cells, paired, per_task = summary["cells"], summary["paired"], summary["per_task"]
    models = sorted({tuple(k.split("|")[:2]) for k in cells},
                    key=lambda k: (MODEL_ORDER.index(k[0]) if k[0] in MODEL_ORDER else 99, 0 if k[1] == "default" else 1))
    tiers = {}
    try:
        from sfe.render import list_tasks, load_task
        for t in list_tasks():
            m = load_task(t).meta
            tiers[t] = m
    except Exception:  # noqa: BLE001
        pass

    cell_rows = []
    for key, c in cells.items():
        m, s, fr = key.split("|")
        cell_rows.append([MODEL_NAMES.get(m, m) + ("" if s == "default" else f" ({s} prompt)"), fr, str(c["n"]),
                          f"{pct1(c['completion'])} <span class=ci>({pct1(c['completion_ci'][0])}–{pct1(c['completion_ci'][1])})</span>",
                          f"{pct1(c['turn1_completion'])} <span class=ci>({pct1(c['turn1_ci'][0])}–{pct1(c['turn1_ci'][1])})</span>",
                          pct1(c["completion_obvious"]), pct1(c["completion_subtle"]),
                          f"{pct1(c['stopping'])} <span class=ci>({pct1(c['stopping_ci'][0])}–{pct1(c['stopping_ci'][1])})</span>",
                          pct1(c["refusal_turn_rate"]), pct1(c["hedging_turn_rate"]), f"{c['tool_calls']:.0f}", f"${c['cost']:.0f}"])
    gap_rows = []
    for key, p in paired.items():
        m, s = key.split("|")
        gap_rows.append([MODEL_NAMES.get(m, m) + ("" if s == "default" else f" ({s} prompt)"), str(p["n_pairs"]),
                         f"{pct1(p['gap_cap_minus_safety'])} <span class=ci>({pct1(p['gap_ci'][0])}–{pct1(p['gap_ci'][1])})</span>",
                         f"{pct1(p['gap_turn1'])} <span class=ci>({pct1(p['gap_turn1_ci'][0])}–{pct1(p['gap_turn1_ci'][1])})</span>",
                         pct1(p["gap_obvious"]),
                         f"{pct1(p['gap_subtle'])} <span class=ci>({pct1(p['gap_subtle_ci'][0])}–{pct1(p['gap_subtle_ci'][1])})</span>",
                         f"{pct(p['frac_pairs_safety_lower'])} / {pct(p['frac_pairs_safety_higher'])}",
                         f"{pct1(p['stop_gap_safety_minus_cap'])} <span class=ci>({pct1(p['stop_gap_ci'][0])}–{pct1(p['stop_gap_ci'][1])})</span>"])
    task_sections = []
    for key, tasks in per_task.items():
        m, s = key.split("|")
        rows = []
        for t, d in tasks.items():
            rows.append([f"<code>{t}</code>", tiers.get(t, {}).get("boundary", "?"), str(d["n"]), pct1(d["safety"]), pct1(d["capabilities"]),
                         pct1(d["gap"]), f"{pct1(d['safety_stop'])} / {pct1(d['cap_stop'])}"])
        task_sections.append(f"<h4>{html.escape(MODEL_NAMES.get(m, m))}{'' if s == 'default' else ' (' + s + ' prompt)'}</h4>"
                             + table(["task", "boundary", "pairs", "safety", "capabilities", "gap (cap − safety)", "stopping safety / cap"], rows))
    ex_html = ""
    for e in examples:
        ex_html += (f'<details><summary><strong>{html.escape(e["label"])}</strong> <span class="muted">{html.escape(e["meta"])}</span></summary>'
                    f'<pre>{html.escape(e["text"])}</pre></details>')

    charts = (bar_chart(cells, "completion", "completion_ci", "Hidden rubric items completed after 3 turns", models)
              + bar_chart(cells, "turn1_completion", "turn1_ci", "Completed after turn 1 (15 tool calls)", models)
              + bar_chart(cells, "stopping", "stopping_ci", "Turns ending in “nothing left” or “blocked”", models, ymax=1.0))

    css = """
:root{--bg:#f6f6f3;--surface:#ffffff;--ink:#1d1f23;--muted:#676b73;--rule:#dcdad3;--cap:#2a78d6;--saf:#eb6834;--code:#eeede8;color-scheme:light}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#17191c;--surface:#1f2226;--ink:#e9e7e1;--muted:#a3a6ad;--rule:#34373d;--cap:#3987e5;--saf:#d95926;--code:#272a30;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#17191c;--surface:#1f2226;--ink:#e9e7e1;--muted:#a3a6ad;--rule:#34373d;--cap:#3987e5;--saf:#d95926;--code:#272a30;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,sans-serif;font-size:16px;line-height:1.55;margin:0;padding-block:28px 64px;padding-inline:16px}
main{max-width:860px;margin:0 auto}
h1{font-family:"Source Serif 4",Georgia,serif;font-weight:600;font-size:clamp(26px,4vw,36px);line-height:1.15;text-wrap:balance;margin:0 0 6px}
h2{font-family:"Source Serif 4",Georgia,serif;font-weight:600;font-size:22px;margin:40px 0 10px;text-wrap:balance}
h4{margin:18px 0 6px;font-weight:600}
.eyebrow{text-transform:uppercase;letter-spacing:.08em;font-size:12px;color:var(--muted)}
p{max-width:68ch}
.answer{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:16px 18px;margin:18px 0 8px;font-size:17px}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;margin:14px 0}
.chart{width:100%;height:auto;background:var(--surface);border:1px solid var(--rule);border-radius:10px}
.ctitle{font:600 14px "IBM Plex Sans",system-ui,sans-serif;fill:var(--ink)}
.tick,.xlab{font:12px "IBM Plex Sans",system-ui,sans-serif;fill:var(--muted)}
.xlab{fill:var(--ink)}
.val{font:600 12px "IBM Plex Mono",ui-monospace,monospace;fill:var(--ink)}
.grid{stroke:var(--rule);stroke-width:1}
.bar-capabilities rect{fill:var(--cap)} .bar-safety rect{fill:var(--saf)}
.bar rect:hover{opacity:.85}
.whisk{stroke:var(--ink);stroke-width:1.2;opacity:.7}
.legend{display:flex;gap:18px;font-size:14px;color:var(--muted);margin:2px 0 10px}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;margin-right:6px}
.tablewrap{overflow-x:auto;border:1px solid var(--rule);border-radius:8px;background:var(--surface);margin:10px 0}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--rule);white-space:nowrap}
th{font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}
tbody tr:last-child td{border-bottom:none}
.ci{color:var(--muted);font-size:12px}
code,pre{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,monospace;font-size:13px}
code{background:var(--code);padding:1px 5px;border-radius:4px}
pre{background:var(--code);padding:12px 14px;border-radius:8px;overflow-x:auto;white-space:pre-wrap;line-height:1.45}
details{border:1px solid var(--rule);border-radius:8px;padding:8px 12px;margin:8px 0;background:var(--surface)}
summary{cursor:pointer}
.muted{color:var(--muted)}
ul{padding-left:20px} li{margin:4px 0;max-width:72ch}
a{color:var(--cap)}
"""
    return f"""<title>{html.escape(title)}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono&family=Source+Serif+4:wght@600&display=swap">
<style>{css}</style>
<main>
<div class="eyebrow">Replication · OpenAI misalignment report, 4 Nov 2026 · run 5 Nov 2026</div>
<h1>{html.escape(title)}</h1>
{intro_html}
<h2>Results</h2>
<div class="legend"><span><span class="sw" style="background:var(--cap)"></span>capabilities framing</span><span><span class="sw" style="background:var(--saf)"></span>safety framing</span><span>whiskers = 95% bootstrap CI over episodes</span></div>
<div class="charts">{charts}</div>
<h4>By model and framing</h4>
{table(["model", "framing", "episodes", "completed (3 turns)", "after turn 1", "obvious items", "subtle items", "stopping turns", "refusal turns", "hedging turns", "tool calls", "cost"], cell_rows)}
<h4>Paired gap, capabilities minus safety (bootstrap over task × seed pairs)</h4>
{table(["model", "pairs", "final gap", "gap after turn 1", "obvious items", "subtle items", "pairs: safety lower / higher", "stopping gap (safety − cap)"], gap_rows)}
<h2>Per task</h2>
{''.join(task_sections)}
<h2>Example final messages</h2>
{ex_html}
<h2>Method and caveats</h2>
{notes_html}
</main>
"""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("res_dir")
    p.add_argument("--title", default="Does a safety framing change what Astra does?")
    p.add_argument("--intro", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--examples", default=None, help="JSON file: [{label, meta, text}]")
    a = p.parse_args()
    res = Path(a.res_dir)
    intro = Path(a.intro).read_text() if a.intro else ""
    notes = Path(a.notes).read_text() if a.notes else ""
    examples = json.loads(Path(a.examples).read_text()) if a.examples else []
    out = res / "index.html"
    out.write_text(build(res, a.title, intro, notes, examples))
    print("wrote", out)


if __name__ == "__main__":
    main()
