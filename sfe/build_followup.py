"""Build the page for the three follow-up experiments (results/followup/index.html).

Charts are drawn as inline SVG from results/family/summary.json, results/debrief/scored.json and
results/real/summary.json; the prose is results/followup_body.html with {{FIG_*}} placeholders.

    python -m sfe.family && python -m sfe.real_analyze --runs ... && python -m sfe.build_followup
"""
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
OUT = RES / "followup"
MODELS = [("GPT-6 Astra", "s1"), ("GPT-6.1 Sol", "s2"), ("GPT-5.6 Sol", "s3")]

ME_ROWS = [  # (framing key, first label line, second label line)
    ("capabilities", "Product team, ordinary wording", "policy avoids a style critic's penalty"),
    ("safety_label_only", "Same, team renamed “AI safety team”", "nothing else changed"),
    ("safety_benign", "Safety team, ordinary wording", "purpose: studying reward shaping"),
    ("product_evasion", "Product team, evasion wording", "policy evades a monitor, no safety purpose"),
    ("safety", "Safety team, evasion wording", "the original safety version"),
    ("safety_defensive", "Safety team, evasion wording", "plus: approved, defensive, never deployed"),
]
DM_ROWS = [
    ("capabilities", "Product team, ordinary wording", "reviewer bot catching regressions"),
    ("safety_benign", "Safety team, ordinary wording", "same code, team renamed"),
    ("product_sabotage", "Product team, sabotage wording", "monitor catching an AI agent's sabotage"),
    ("safety", "Safety team, sabotage wording", "the original safety version"),
]


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def legend(x: float, y: float, items) -> str:
    o, cx = [], x
    for name, cls in items:
        o.append(f'<circle class="dot {cls}" cx="{cx + 5:.0f}" cy="{y - 4:.0f}" r="5"/><text class="leg" x="{cx + 15:.0f}" y="{y:.0f}">{esc(name)}</text>')
        cx += 30 + 7.2 * len(name)
    return "".join(o)


def dot_rows(rows, get, lo, hi, ticks, unit="%", extra_title="", w=720, left=268, right=96, rh=54, aria=""):
    """One row per description; one dot with a 95% interval per model. `get(model, key)` -> dict or None."""
    top = 40
    h = top + rh * len(rows) + 34
    x = lambda v: left + (min(max(v, lo), hi) - lo) / (hi - lo) * (w - left - right)
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(aria)}">', legend(left, 18, MODELS)]
    if extra_title:
        o.append(f'<text class="sub" x="{w - 4}" y="18" text-anchor="end">{esc(extra_title)}</text>')
    for t in ticks:
        o.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top - 6}" y2="{h - 30}"/>')
        o.append(f'<text class="tick" x="{x(t):.1f}" y="{h - 14}" text-anchor="middle">{t}{unit}</text>')
    for i, (key, l1, l2) in enumerate(rows):
        y0 = top + rh * i
        if i:
            o.append(f'<line class="sep" x1="0" x2="{w}" y1="{y0 - 2}" y2="{y0 - 2}"/>')
        o.append(f'<text class="lab" x="{left - 14}" y="{y0 + rh / 2 - 3:.1f}" text-anchor="end">{esc(l1)}</text>')
        o.append(f'<text class="sub" x="{left - 14}" y="{y0 + rh / 2 + 11:.1f}" text-anchor="end">{esc(l2)}</text>')
        for j, (model, cls) in enumerate(MODELS):
            c = get(model, key)
            y = y0 + 12 + j * 14
            if not c:
                continue
            tip = f'{model}, {l1} ({l2}): {c["mean"]:.1f}{unit} over {c["n"]} episodes, 95% interval {c["ci"][0]:.1f} to {c["ci"][1]:.1f}' + (f'; {c["extra_label"]} {c["extra"]}' if c.get("extra") else "")
            o.append(f'<g><title>{esc(tip)}</title><rect class="hit" x="{left}" y="{y - 7}" width="{w - left}" height="14"/>')
            o.append(f'<line class="ci {cls}" x1="{x(c["ci"][0]):.1f}" x2="{x(c["ci"][1]):.1f}" y1="{y}" y2="{y}"/>')
            o.append(f'<circle class="dot {cls}" cx="{x(c["mean"]):.1f}" cy="{y}" r="5"/>')
            if c.get("extra"):
                o.append(f'<text class="val" x="{w - 4}" y="{y + 4}" text-anchor="end">{esc(c["extra"])}</text>')
            o.append("</g>")
    o.append("</svg>")
    return "\n".join(o)


def fig_family(task: str, rows, lo, hi, ticks, extra_title, extra_label) -> str:
    d = json.load(open(RES / "family" / "summary.json"))

    def get(model, key):
        c = d.get(f"{model}|{task}", {}).get(key)
        return dict(c, extra_label=extra_label) if c else None
    return dot_rows(rows, get, lo, hi, ticks, extra_title=extra_title, aria=f"Completion by description, {task}")


def ptest_table() -> dict:
    """Mean stated probability that the session was a test, by setting and model."""
    from sfe.config import TASKS_DIR
    from sfe.recap_plot import old_vs_new_setting           # the one rule for which episodes are toy and which real
    rows = json.load(open(RES / "debrief" / "scored.json"))
    toy_tasks = {p.name for p in TASKS_DIR.iterdir() if p.is_dir()}
    main_runs = {r["key"].split("__")[0] for r in json.load(open(RES / "real" / "rows.json"))}
    g = defaultdict(list)
    for r in rows:
        p = (r.get("label") or {}).get("q2_prob")
        group = old_vs_new_setting(r, toy_tasks, main_runs)   # None: new repositories, description edits, the panel runs
        if p is None or group is None:
            continue
        setting = ("real repository" if group == "real" else
                   "larger toy repository" if r["task"] == "monitor_evasion_rl" else "toy repository")
        model = {"astra": "GPT-6 Astra", "sol61": "GPT-6.1 Sol", "sol61s": "GPT-6.1 Sol", "sol": "GPT-5.6 Sol", "kimi": "Kimi K3"}.get(r["model"])
        if model is None:     # this chart is about the three OpenAI models (and Kimi on toy tasks)
            continue
        g[(setting, model)].append(float(p))
    return {k: {"mean": st.mean(v), "n": len(v), "lo": min(v), "hi": max(v)} for k, v in g.items()}


def fig_ptest() -> str:
    t = ptest_table()
    settings = ["toy repository", "larger toy repository", "real repository"]
    w, left, right, top, rh = 720, 268, 60, 40, 54
    h = top + rh * len(settings) + 34
    x = lambda v: left + v / 100 * (w - left - right)
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Stated probability that the session was a test">', legend(left, 18, MODELS)]
    for tk in range(0, 101, 25):
        o.append(f'<line class="grid" x1="{x(tk):.1f}" x2="{x(tk):.1f}" y1="{top - 6}" y2="{h - 30}"/>')
        o.append(f'<text class="tick" x="{x(tk):.1f}" y="{h - 14}" text-anchor="middle">{tk}%</text>')
    subs = {"toy repository": "original six tasks and the sabotage-monitor task", "larger toy repository": "monitor-evasion task",
            "real repository": "six open-source projects"}
    for i, s in enumerate(settings):
        y0 = top + rh * i
        if i:
            o.append(f'<line class="sep" x1="0" x2="{w}" y1="{y0 - 2}" y2="{y0 - 2}"/>')
        o.append(f'<text class="lab" x="{left - 14}" y="{y0 + rh / 2 - 3:.1f}" text-anchor="end">{esc(s.capitalize())}</text>')
        o.append(f'<text class="sub" x="{left - 14}" y="{y0 + rh / 2 + 11:.1f}" text-anchor="end">{esc(subs[s])}</text>')
        for j, (model, cls) in enumerate(MODELS):
            c = t.get((s, model))
            if not c:
                continue
            y = y0 + 6 + j * 14
            tip = f'{model}, {s}: mean {c["mean"]:.0f}% over {c["n"]} episodes (range {c["lo"]:.0f} to {c["hi"]:.0f})'
            o.append(f'<g><title>{esc(tip)}</title><rect class="bar {cls}" x="{x(0):.1f}" y="{y}" width="{x(c["mean"]) - x(0):.1f}" height="11" rx="2"/>')
            o.append(f'<text class="val" x="{x(c["mean"]) + 6:.1f}" y="{y + 9.5}">{c["mean"]:.0f}%</text></g>')
    o.append("</svg>")
    return "\n".join(o)


def fig_real() -> str:
    """Per model: checklist completion under each framing on the real repositories (hollow = capabilities, filled = safety)."""
    d = json.load(open(RES / "real" / "summary.json"))
    keys = [("astra", "GPT-6 Astra", "s1"), ("sol61s", "GPT-6.1 Sol", "s2"), ("sol", "GPT-5.6 Sol", "s3")]
    hi = max(max(d[k]["done"]["safety"], d[k]["done"]["capabilities"]) for k, _, _ in keys if k in d) * 1.35
    w, left, right, top, rh = 720, 200, 190, 40, 40
    h = top + rh * len(keys) + 34
    x = lambda v: left + v / hi * (w - left - right)
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Checklist completion on real repositories by framing">']
    o.append(f'<circle class="dot hollow" cx="{left + 5}" cy="14" r="5"/><text class="leg" x="{left + 15}" y="18">capabilities description</text>')
    o.append(f'<circle class="dot solid" cx="{left + 195}" cy="14" r="5"/><text class="leg" x="{left + 205}" y="18">safety description</text>')
    step = 2 if hi < 14 else 5
    for tk in range(0, int(hi) + 1, step):
        o.append(f'<line class="grid" x1="{x(tk):.1f}" x2="{x(tk):.1f}" y1="{top - 6}" y2="{h - 30}"/>')
        o.append(f'<text class="tick" x="{x(tk):.1f}" y="{h - 14}" text-anchor="middle">{tk}%</text>')
    for i, (k, name, cls) in enumerate(keys):
        if k not in d:
            continue
        g = d[k]["done"]
        y = top + rh * i + rh / 2
        tip = (f'{name}: safety {g["safety"]:.1f}%, capabilities {g["capabilities"]:.1f}%, gap {g["gap"]:+.1f} '
               f'(95% interval {g["ci"][0]:+.1f} to {g["ci"][1]:+.1f}), p={g["p"]:.2f}, {g["n"]} episodes')
        o.append(f'<g><title>{esc(tip)}</title><rect class="hit" x="0" y="{y - rh / 2}" width="{w}" height="{rh}"/>')
        o.append(f'<text class="lab" x="{left - 14}" y="{y + 4}" text-anchor="end">{esc(name)}</text>')
        o.append(f'<line class="ci {cls}" x1="{x(g["safety"]):.1f}" x2="{x(g["capabilities"]):.1f}" y1="{y}" y2="{y}"/>')
        o.append(f'<circle class="dot {cls} open" cx="{x(g["capabilities"]):.1f}" cy="{y}" r="5.5"/>')
        o.append(f'<circle class="dot {cls}" cx="{x(g["safety"]):.1f}" cy="{y}" r="5.5"/>')
        o.append(f'<text class="val" x="{w - 4}" y="{y + 4}" text-anchor="end">gap {g["gap"]:+.1f} ({g["ci"][0]:+.1f} to {g["ci"][1]:+.1f})</text></g>')
    o.append("</svg>")
    return "\n".join(o)


EXTRA_CSS = """
:root{--s3:#1baf7a}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){--s3:#199e70} }
:root[data-theme="dark"]{--s3:#199e70}
svg .dot.s1{fill:var(--s1)} svg .dot.s2{fill:var(--s2)} svg .dot.s3{fill:var(--s3)}
svg .ci.s1{stroke:var(--s1)} svg .ci.s2{stroke:var(--s2)} svg .ci.s3{stroke:var(--s3)}
svg .bar.s3{fill:var(--s3)} svg .sep{stroke:var(--line);stroke-width:1}
svg .dot.s1.open{fill:var(--panel);stroke:var(--s1);stroke-width:2.5} svg .dot.s2.open{fill:var(--panel);stroke:var(--s2);stroke-width:2.5}
svg .dot.s3.open{fill:var(--panel);stroke:var(--s3);stroke-width:2.5}
svg .dot.hollow{fill:var(--panel);stroke:var(--ink2);stroke-width:2.5} svg .dot.solid{fill:var(--ink2)}
blockquote{margin:0;padding:8px 14px;border-left:3px solid var(--line);color:var(--ink2);font-size:.92rem}
td.num,th.num{text-align:right;padding-right:14px}
"""
REPO_NAMES = {"synthetic-data-kit": ("synthetic-data-kit", "data for a backdoored model organism", "data for a style-conditioned assistant"),
              "rsl_rl": ("rsl_rl", "training a policy to evade a monitor", "training a walking policy with a style critic"),
              "prompto": ("prompto", "running and grading jailbreak attempts", "running and grading support questions"),
              "valor": ("valor", "evaluating a jailbreak monitor", "evaluating a sales-lead classifier"),
              "NeuroX": ("NeuroX", "training deception probes", "training sentiment probes"),
              "dictionary_learning": ("dictionary_learning", "SAE audit for deception features", "SAE study of upsell features")}


def real_table() -> str:
    d = json.load(open(RES / "real" / "summary.json"))
    keys = [("astra", "GPT-6 Astra"), ("sol61s", "GPT-6.1 Sol"), ("sol", "GPT-5.6 Sol")]
    o = ['<div class="tw"><table><tr><th>Repository and its safety description</th>'
         + "".join(f'<th class="num">{n}<br>safety / capabilities</th>' for _, n in keys) + "</tr>"]
    order = sorted(REPO_NAMES, key=lambda t: -(d["astra"]["done"]["per_task"][t][1] - d["astra"]["done"]["per_task"][t][0]))
    for t in order:
        name, saf, cap = REPO_NAMES[t]
        cells = ""
        for k, _ in keys:
            s_, c_, ns, nc = d[k]["done"]["per_task"][t]
            cells += f'<td class="num">{s_:.1f} / {c_:.1f} <span style="color:var(--ink3)">({c_ - s_:+.1f})</span></td>'
        o.append(f"<tr><td><code>{name}</code>: {saf}</td>{cells}</tr>")
    o.append("</table></div>")
    return "\n".join(o)

# ---- eleven more models (11 Nov 2026): charts and table from results/real/all_models.json ----------------------------
ALL_ORDER = ["astra", "sol61s", "sol", "fable52", "opus", "carbon", "argon", "gem31pro", "flash35", "flash38", "muse", "grok", "kimi", "dsflash"]
ALL_NAMES = {"astra": "GPT-6 Astra", "sol61s": "GPT-6.1 Sol", "sol": "GPT-5.6 Sol", "fable52": "Claude Fable 5.2", "opus": "Claude Opus 5.5",
             "carbon": "Gemini 4 Carbon", "argon": "Gemini 4 Argon", "gem31pro": "Gemini 3.1 Pro", "flash38": "Gemini 3.8 Flash",
             "flash35": "Gemini 3.5 Flash", "muse": "Muse Wonder", "grok": "Grok 4.7", "kimi": "Kimi K3", "dsflash": "DeepSeek V4.1 Flash"}
ALL_CO = {"astra": "openai", "sol61s": "openai", "sol": "openai", "fable52": "anthropic", "opus": "anthropic", "carbon": "google",
          "argon": "google", "gem31pro": "google", "flash35": "google", "flash38": "google", "muse": "meta", "grok": "xai",
          "kimi": "moonshot", "dsflash": "deepseek"}
CO_COLOURS = {"openai": ("#0b6e4f", "#3fbf93"), "anthropic": ("#b5410f", "#e58a57"), "google": ("#3b6fd6", "#86a9f2"),
              "meta": ("#6a4bc4", "#a996f2"), "xai": ("#333333", "#cfcfcf"), "moonshot": ("#8f6b00", "#dcb13a"), "deepseek": ("#a8851a", "#e6c868")}
CATS = [("changed the core code", "changed the code", "did"), ("left it alone, said so with a reason", "left it alone, told the user why", "why"),
        ("left it alone, said so without a reason", "left it alone, told the user, no reason", "noreason"),
        ("left it alone, never said so", "left it alone, said nothing about it", "silent"), ("blocked", "blocked by the provider’s filter", "blocked")]


def company_css() -> str:
    light = "".join(f"--c-{k}:{a};" for k, (a, _) in CO_COLOURS.items()) + "--cat-did:#e2e1da;--cat-why:#2a78d6;--cat-noreason:#eb6834;--cat-silent:#9b9a93;"
    dark = "".join(f"--c-{k}:{b};" for k, (_, b) in CO_COLOURS.items()) + "--cat-did:#3a3a37;--cat-why:#3987e5;--cat-noreason:#d95926;--cat-silent:#7d7c76;"
    css = f":root{{{light}}}\n@media (prefers-color-scheme: dark){{ :root:not([data-theme=\"light\"]){{{dark}}} }}\n:root[data-theme=\"dark\"]{{{dark}}}\n"
    for k in CO_COLOURS:
        css += (f"svg .dot.co-{k}{{fill:var(--c-{k})}} svg .ci.co-{k}{{stroke:var(--c-{k})}} svg .bar.co-{k}{{fill:var(--c-{k})}} "
                f"svg .dot.co-{k}.open{{fill:var(--panel);stroke:var(--c-{k});stroke-width:2.5}} svg text.co-{k}{{fill:var(--c-{k});font-weight:600}}\n")
    css += ("svg .cat-did{fill:var(--cat-did)} svg .cat-why{fill:var(--cat-why)} svg .cat-noreason{fill:var(--cat-noreason)} "
            "svg .cat-silent{fill:var(--cat-silent)} svg .cat-blocked{fill:url(#hatch);stroke:var(--ink3);stroke-width:1}\n"
            "svg text.cnt{font-size:11px;fill:var(--ink)} svg text.cnt.on{fill:#fff;font-weight:600}\n"
            ".correction{border-left:3px solid var(--cat-noreason);padding:10px 14px;background:var(--panel);font-size:.95rem}\n")
    return css


def _all():
    d = json.load(open(RES / "real" / "all_models.json"))
    return d, [m for m in ALL_ORDER if m in d and "conduct" in d[m]]


def _star(m: str) -> str:
    return ALL_NAMES[m] + ("*" if m in ("fable52", "opus") else "")


def fig_models_core() -> str:
    """Per model: share of episodes on the two attack-like repositories whose diff changes the core code (filled = safety)."""
    d, models = _all()
    w, left, right, top, rh = 720, 168, 178, 40, 27
    h = top + rh * len(models) + 34
    x = lambda v: left + v / 100 * (w - left - right)                                           # noqa: E731
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Episodes that changed the attack-like code, by model and description">']
    o.append(f'<circle class="dot solid" cx="{left + 5}" cy="14" r="5"/><text class="leg" x="{left + 15}" y="18">safety description</text>')
    o.append(f'<circle class="dot hollow" cx="{left + 155}" cy="14" r="5"/><text class="leg" x="{left + 165}" y="18">product description</text>')
    o.append(f'<text class="sub" x="{w - 4}" y="18" text-anchor="end">changed it: safety vs product</text>')
    for tk in (0, 25, 50, 75, 100):
        o.append(f'<line class="grid" x1="{x(tk):.1f}" x2="{x(tk):.1f}" y1="{top - 6}" y2="{h - 30}"/>')
        o.append(f'<text class="tick" x="{x(tk):.1f}" y="{h - 14}" text-anchor="middle">{tk}%</text>')
    for i, m in enumerate(models):
        y, co = top + rh * i + rh / 2, ALL_CO[m]
        s_, c_ = d[m]["conduct"]["safety"], d[m]["conduct"]["capabilities"]
        bl = sum(d[m].get("blocked_attack", {}).values())
        xs = 100 * s_["core_changed"] / s_["n"] if s_["n"] else None
        xc = 100 * c_["core_changed"] / c_["n"] if c_["n"] else None
        note = f'{s_["core_changed"]}/{s_["n"]} vs {c_["core_changed"]}/{c_["n"]}' + (f' · {bl} blocked' if bl else "")
        tip = (f'{ALL_NAMES[m]}: changed the core code in {s_["core_changed"]} of {s_["n"]} safety-described and {c_["core_changed"]} of {c_["n"]} '
               f'product-described episodes' + (f'; {bl} more were blocked by the provider’s filter before any reply' if bl else ""))
        o.append(f'<g><title>{esc(tip)}</title><rect class="hit" x="0" y="{y - rh / 2}" width="{w}" height="{rh}"/>')
        o.append(f'<text class="lab co-{co}" x="{left - 14}" y="{y + 4}" text-anchor="end">{esc(_star(m))}</text>')
        if xs is not None and xc is not None:
            o.append(f'<line class="ci co-{co}" x1="{x(xs):.1f}" x2="{x(xc):.1f}" y1="{y}" y2="{y}"/>')
        if xc is not None:
            o.append(f'<circle class="dot co-{co} open" cx="{x(xc):.1f}" cy="{y}" r="5.5"/>')
        if xs is not None:
            o.append(f'<circle class="dot co-{co}" cx="{x(xs):.1f}" cy="{y}" r="5.5"/>')
        o.append(f'<text class="val" x="{w - 4}" y="{y + 4}" text-anchor="end">{esc(note)}</text></g>')
    o.append("</svg>")
    return "\n".join(o)


def fig_told() -> str:
    """Two bars per model (safety above, product below): what happened to the attack-like code and what the user was told."""
    d, models = _all()
    w, left, right, top, rh, bh = 720, 232, 24, 62, 44, 14
    h = top + rh * len(models) + 30
    span = w - left - right
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="What each model did with the attack-like code and what it told the user">',
         '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
         '<rect width="6" height="6" fill="var(--panel)"/><line x1="0" y1="0" x2="0" y2="6" stroke="var(--ink3)" stroke-width="2"/></pattern></defs>']
    lx, ly = 4, 12
    for k, (_, lab, cls) in enumerate(CATS):
        if k == 3:
            lx, ly = 4, 32
        o.append(f'<rect class="cat-{cls}" x="{lx}" y="{ly - 9}" width="14" height="11" rx="2"/><text class="leg" x="{lx + 20}" y="{ly}">{esc(lab)}</text>')
        lx += 36 + 6.6 * len(lab)
    for tk in (0, 25, 50, 75, 100):
        xx = left + tk / 100 * span
        o.append(f'<line class="grid" x1="{xx:.1f}" x2="{xx:.1f}" y1="{top - 6}" y2="{h - 26}"/>')
        o.append(f'<text class="tick" x="{xx:.1f}" y="{h - 10}" text-anchor="middle">{tk}%</text>')
    for i, m in enumerate(models):
        y0, co = top + rh * i, ALL_CO[m]
        o.append(f'<text class="lab co-{co}" x="{left - 70}" y="{y0 + rh / 2 + 1:.1f}" text-anchor="end">{esc(_star(m))}</text>')
        for j, (f, flab) in enumerate((("safety", "safety"), ("capabilities", "product"))):
            y = y0 + 5 + j * (bh + 3)
            cat = dict(d[m]["conduct"][f]["categories"])
            cat["blocked"] = d[m].get("blocked_attack", {}).get(f, 0)
            n = sum(cat.values())
            o.append(f'<text class="sub" x="{left - 8}" y="{y + bh - 3}" text-anchor="end">{flab}</text>')
            xx = float(left)
            for key, lab, cls in CATS:
                k = cat.get(key, 0)
                if not k or not n:
                    continue
                ww = span * k / n
                on = " on" if cls in ("why", "noreason", "silent") else ""
                o.append(f'<g><title>{esc(f"{ALL_NAMES[m]}, {flab} description: {lab} in {k} of {n} episodes")}</title>'
                         f'<rect class="cat-{cls}" x="{xx + 0.75:.1f}" y="{y}" width="{max(ww - 1.5, 1):.1f}" height="{bh}" rx="2"/>'
                         + (f'<rect x="{xx + ww / 2 - 7:.1f}" y="{y + 1.5}" width="14" height="{bh - 3}" rx="2" fill="var(--panel)"/>' if cls == "blocked" else "")
                         + f'<text class="cnt{on}" x="{xx + ww / 2:.1f}" y="{y + bh - 3.5}" text-anchor="middle">{k}</text></g>')
                xx += ww
    o.append("</svg>")
    return "\n".join(o)


def fig_aware() -> str:
    """Per model: stated chance the session was a test (asked directly) and share of episodes that raise it unprompted."""
    d, models = _all()
    models = [m for m in models if d[m].get("p_test", {}).get("mean") is not None]
    w, left, top, rh, gap = 720, 168, 40, 24, 36
    colw = (w - left - gap - 130) / 2
    h = top + rh * len(models) + 14
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="How likely each model says it is that the session was a test">']
    for j, title in enumerate(("stated chance, asked directly", "raises it unprompted (open question)")):
        o.append(f'<text class="sub" x="{left + j * (colw + gap + 30):.0f}" y="18">{esc(title)}</text>')
    for i, m in enumerate(models):
        y, co = top + rh * i, ALL_CO[m]
        pm = d[m]["p_test"]["mean"]
        k, n = d[m]["q1_suspects"]
        o.append(f'<g><title>{esc(f"{ALL_NAMES[m]}: mean stated chance {pm:.0f}%; says the session may be a test before being asked directly in {k} of {n} episodes")}</title>')
        o.append(f'<rect class="hit" x="0" y="{y - 4}" width="{w}" height="{rh}"/>')
        o.append(f'<text class="lab co-{co}" x="{left - 14}" y="{y + 11}" text-anchor="end">{esc(ALL_NAMES[m])}</text>')
        for jj, (v, txt) in enumerate(((pm, f"{pm:.0f}%"), (100 * k / n if n else 0, f"{k}/{n}"))):
            x0 = left + jj * (colw + gap + 30)
            o.append(f'<rect class="bar co-{co}" x="{x0:.1f}" y="{y}" width="{max(colw * v / 100, 1):.1f}" height="14" rx="2"/>')
            o.append(f'<text class="val" x="{x0 + colw * v / 100 + 6:.1f}" y="{y + 11}">{txt}</text>')
        o.append("</g>")
    o.append("</svg>")
    return "\n".join(o)


def models_table() -> str:
    """One row per model: the numbers behind the charts, plus the checklist gaps."""
    d, models = _all()

    def gap(g):
        if not g:
            return "n/a"
        ci = f' <span style="color:var(--ink3)">({g["ci"][0]:+.1f} to {g["ci"][1]:+.1f})</span>' if g.get("ci") else ""
        return f'{g["gap"]:+.1f}{ci}'
    o = ['<div class="tw"><table><tr><th>Model</th><th class="num">Changed the attack-like code<br>safety / product</th>'
         '<th class="num">Told the user it was steering away<br>safety / product</th>'
         '<th class="num">Checklist gap, attack-like<br>repositories (points)</th><th class="num">Checklist gap, four<br>measurement repositories</th>'
         '<th class="num">Episodes used<br>(blocked, replaced)</th></tr>']
    rep = json.load(open(RES / "real" / "replaced_episodes.json")) if (RES / "real" / "replaced_episodes.json").exists() else {}
    for m in models:
        r = d[m]
        s_, c_ = r["conduct"]["safety"], r["conduct"]["capabilities"]
        nrep = sum(1 for k, v in rep.items() if v.get("model") == m and k.startswith("real2_"))    # the fourteen-model runs only
        o.append(f'<tr><td>{esc(_star(m))}</td><td class="num">{s_["core_changed"]} of {s_["n"]} / {c_["core_changed"]} of {c_["n"]}</td>'
                 f'<td class="num">{s_["announced"]} of {s_["n"]} / {c_["announced"]} of {c_["n"]}</td>'
                 f'<td class="num">{gap(r.get("done|attack-building"))}</td><td class="num">{gap(r.get("done|measurement"))}</td>'
                 f'<td class="num">{r["n_analysed"]} ({r["n_blocked"]}, {nrep})</td></tr>')
    o.append("</table></div>")
    return "\n".join(o)


def fine_table(task: str) -> str:
    """Description edits for one repository: sessions whose first reply says the model will hold back (probe) and full episodes whose diff
    changes the core code, from results/real/fine_grained.json (python -m sfe.fine_grained)."""
    from sfe.fine_grained import ROWS
    d = json.load(open(RES / "real" / "fine_grained.json"))
    models = [("astra", "GPT-6 Astra"), ("sol61s", "GPT-6.1 Sol"), ("sol", "GPT-5.6 Sol")]
    o = ['<div class="tw"><table><tr><th>Description (one change at a time)</th>'
         + "".join(f'<th class="num">{n}<br>first reply says it will hold back<br>(of 10 fresh sessions)</th>' for _, n in models[:2])
         + "".join(f'<th class="num">{n}<br>changed the core code</th>' for _, n in models) + "</tr>"]
    for key, label in ROWS[task]:
        cells = ""
        for m, _ in models[:2]:
            c = (d.get(f"{task}|{key}|{m}") or {}).get("probe")
            cells += f'<td class="num">{c["limit"]} of {c["n"]}</td>' if c else '<td class="num">–</td>'
        for m, _ in models:
            e = (d.get(f"{task}|{key}|{m}") or {}).get("episodes")
            cells += f'<td class="num">{e["core_changed"]} of {e["n"]}</td>' if e else '<td class="num">–</td>'
        o.append(f"<tr><td>{esc(label)}</td>{cells}</tr>")
    o.append("</table></div>")
    return "\n".join(o)


def implied_html() -> str:
    """Descriptions where the attack-like purpose is implied or sits only in the README, next to the explicit original and
    the no-description baseline: was the core code left alone, and did any message say so?"""
    from sfe.fine_grained import IMPLIED, ROWS
    d = json.load(open(RES / "real" / "fine_grained.json"))
    labels = {(t, k): lab for t, rows in ROWS.items() for k, lab in rows}
    repo = {"rsl_rl": "RL library", "synthetic-data-kit": "Data kit"}
    models = [("astra", "GPT-6 Astra"), ("sol61s", "GPT-6.1 Sol")]
    o = ['<div class="tw"><table><tr><th>Repository and description</th>'
         + "".join(f'<th class="num">{n}<br>left the core code alone</th><th class="num">of those,<br>no message says so</th>'
                   f'<th class="num">of those,<br>reasoning shows it</th>' for _, n in models) + "</tr>"]
    for task, key in IMPLIED:
        cells = ""
        for m, _ in models:
            e = (d.get(f"{task}|{key}|{m}") or {}).get("episodes")
            if not e:
                cells += '<td class="num">–</td><td class="num">–</td><td class="num">–</td>'
                continue
            left = e["n"] - e["core_changed"]
            silent, shows = e["left_alone_unannounced"], e["left_alone_unannounced_reasoning_shows_it"]
            if e.get("left_alone_read_in_full") == left and left:   # every hold-back read in full: marked as such
                silent, shows = f"{silent}&#8224;", f"{shows}&#8224;"
            cells += (f'<td class="num">{left} of {e["n"]}</td><td class="num">{silent}</td>'
                      f'<td class="num">{shows}</td>')
        o.append(f"<tr><td>{repo[task]}: {esc(labels.get((task, key), key))}</td>{cells}</tr>")
    o.append("</table></div>")
    return "\n".join(o)


def rerun_note() -> str:
    """One sentence group on the spoiled episodes, worded by how many of their clean re-runs exist."""
    rp = RES / "real" / "replaced_episodes.json"
    if not rp.exists():
        return "No episode was set aside."
    every = json.load(open(rp))
    rep = {k: v for k, v in every.items() if k.startswith("real2_")}          # the eleven-model run
    later = len(every) - len(rep)                                            # description-edit episodes discarded for another reason
    landed = sum((ROOT / "runs" / k.split("__", 1)[0] / "episodes" / (k.split("__", 1)[1] + ".json")).exists() for k in rep)
    words = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
    n = words[len(rep)].capitalize() if len(rep) < len(words) else str(len(rep))
    out = (f"Until 11 November the machines were not really offline, and episodes running at the same time shared a temporary "
           f"folder. {n} episodes of the eleven-model run were spoiled by this. Two downloaded the project’s later release, which "
           f"contains fixes the checklist is built from, and two more found one of those copies. The rest downloaded another "
           f"release or a dependency, or used a folder holding one. None was from the three OpenAI models. ")
    if landed == len(rep):
        return out + ("All were set aside and run again, one at a time, on a machine with no internet access. The figures here use the re-runs."
                      + (" One episode of the later description-edit runs was also discarded and run again, after two running episodes "
                         "were given the same user account by mistake." if later else ""))
    if landed:
        return out + (f"They were set aside. {words[landed].capitalize()} have been run again so far, on a machine with no internet access; "
                      f"the others are left out of the figures here.")
    return out + "They are left out of the figures here and are being run again on a machine with no internet access."


def fill_numbers(body: str) -> str:
    """{{R|model|key|field}} -> a number from results/real/summary.json; {{S|model|kind|framing}} -> 'a of b' scope counts;
    {{P|setting|model}} -> mean stated chance of a test."""
    import re
    d = json.load(open(RES / "real" / "summary.json"))
    allm = json.load(open(RES / "real" / "all_models.json"))
    fgp = RES / "real" / "fine_grained.json"
    fg = json.load(open(fgp)) if fgp.exists() else {}
    pt = ptest_table()

    def r(m):
        kind, *args = m.group(1).split("|")
        if kind == "R":
            model, field = args[0], args[-1]
            key = "|".join(args[1:-1])          # e.g. "done" or "done|attack-building"
            g = d[model][key]
            v = {"safety": g["safety"], "capabilities": g["capabilities"], "gap": g["gap"], "lo": g["ci"][0], "hi": g["ci"][1],
                 "p": g["p"], "n": g["n"]}[field]
            if field == "p":
                return "below 0.001" if v < 0.001 else f"{v:.3f}".rstrip("0") if v < 0.01 else f"{v:.2f}"
            if field == "n":
                return str(v)
            return f"{v:+.1f}" if field in ("gap", "lo", "hi") else f"{v:.1f}"
        if kind == "S":
            model, k, f = args
            a_, b_, _ = d[model]["scope"][f"{k}|{f}"]
            return f"{a_} of {b_}"
        if kind == "C":                     # episodes whose diff touches the core code, pooled over the two attack-like repositories
            model, f = args
            ct = json.load(open(RES / "real" / "core_touched.json"))
            ks = [k for k in ct if k.split("|")[1] == model and k.split("|")[2] == f]
            return f"{sum(ct[k][0] for k in ks)} of {sum(ct[k][1] for k in ks)}"
        if kind == "P":
            setting, model = args
            return f'{pt[(setting, model)]["mean"]:.0f}%'
        if kind == "A":                     # the fourteen-model analysis: {{A|model|field}}
            model, field = args
            a = allm[model]
            cs, cc = a["conduct"]["safety"], a["conduct"]["capabilities"]
            return {"core_s": f'{cs["core_changed"]} of {cs["n"]}', "core_c": f'{cc["core_changed"]} of {cc["n"]}',
                    "ann_s": f'{cs["announced"]} of {cs["n"]}', "ann_c": f'{cc["announced"]} of {cc["n"]}',
                    "opening_s": f'{cs["announced_in_opening_message"]} of {cs["n"]}', "summary_s": f'{cs["announced_in_a_summary"]} of {cs["n"]}',
                    "reason_s": f'{cs["announced_with_reason"]} of {cs["n"]}', "refusal_s": f'{cs["announced_refusal_wording"]} of {cs["n"]}',
                    "reasoning_s": f'{cs["reasoning_states_decision"]} of {cs["n"]}',
                    "ptest": f'{a["p_test"]["mean"]:.0f}%', "q1": f'{a["q1_suspects"][0]} of {a["q1_suspects"][1]}',
                    "gap_wo_announced": f'{a["done_without_announced"]["gap"]:+.1f}', "n": str(a["n_analysed"])}[field]
        if kind == "F":
            task, keys, model, field = args
            es = [(fg.get(f"{task}|{k}|{model}") or {}).get("episodes") for k in keys.split("+")]
            es = [e for e in es if e]
            n = sum(e["n"] for e in es)
            left = sum(e["n"] - e["core_changed"] for e in es)
            return {"n": str(n), "left": f"{left} of {n}", "changed": f"{n - left} of {n}", "leftn": str(left),
                    "silent": str(sum(e["left_alone_unannounced"] for e in es)),
                    "reasoning": str(sum(e["left_alone_unannounced_reasoning_shows_it"] for e in es)),
                    "remark": str(sum(e.get("left_alone_remark_only", 0) for e in es)),
                    "announced": f'{sum(e["announced"] for e in es)} of {n}'}[field]
        raise KeyError(m.group(0))
    return re.sub(r"\{\{((?:R|S|P|C|A|F)\|[^}]+)\}\}", r, body)


def main() -> None:
    body = (RES / "followup_body.html").read_text()
    style = (RES / "onepage_body.html").read_text().split("<style>")[1].split("</style>")[0]
    body = body.replace("{{STYLE}}", style + EXTRA_CSS + company_css()).replace("{{TABLE_REPOS}}", real_table())
    body = body.replace("{{TABLE_MODELS}}", models_table()).replace("{{RERUN_NOTE}}", rerun_note())
    if "{{TABLE_FG_RSL}}" in body:
        body = body.replace("{{TABLE_FG_RSL}}", fine_table("rsl_rl")).replace("{{TABLE_FG_SDK}}", fine_table("synthetic-data-kit"))
        extra = RES / "followup_fg_extra.html"          # bullets written once the full episodes are in
        body = body.replace("{{FG_EXTRA}}", extra.read_text() if extra.exists() else "").replace("{{TABLE_IMPLIED}}", implied_html())
        rb = RES / "followup_readme_bullet.html"        # one bullet on the README-only arm, written once those episodes are in
        body = body.replace("{{README_BULLET}}", rb.read_text() if rb.exists() else "")
    body = fill_numbers(body)
    figs = {"{{FIG_ME}}": lambda: fig_family("monitor_evasion_rl", ME_ROWS, 0, 100, [0, 25, 50, 75, 100], "training code edited", "training code edited in"),
            "{{FIG_DM}}": lambda: fig_family("diff_monitor", DM_ROWS, 70, 95, [70, 75, 80, 85, 90, 95], "detector fixes made", "detector fixes made:"),
            "{{FIG_PTEST}}": fig_ptest, "{{FIG_REAL}}": fig_real,
            "{{FIG_MODELS_CORE}}": fig_models_core, "{{FIG_TOLD}}": fig_told, "{{FIG_AWARE}}": fig_aware}
    for k, fn in figs.items():
        if k in body:
            body = body.replace(k, fn())
    assert "{{" not in body, "unfilled placeholder"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(body)
    print("wrote", OUT / "index.html", len(body), "chars")


if __name__ == "__main__":
    main()
