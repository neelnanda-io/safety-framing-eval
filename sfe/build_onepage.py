"""Build the one-page summary (results/onepage/index.html) from the saved summary JSON files.

Run:  python -m sfe.build_onepage
The two charts are drawn as inline SVG straight from results/summary/*.json, so they cannot drift from the numbers.
The prose lives in results/onepage_body.html, with {{FIG1}} and {{FIG2}} placeholders.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMMARY = ROOT / "results" / "summary"
OUT = ROOT / "results" / "onepage"

TASK_NAMES = {  # safety-framed name of each task, in plain words
    "monitor_evasion_rl": "Training a policy to evade a monitor",
    "prompt_augment": "Augmenting red-team attack prompts",
    "diff_monitor": "Evaluating a sabotage monitor",
    "organism_data": "Data for a backdoored model organism",
    "clf_eval": "Evaluating a jailbreak monitor",
    "jailbreak_corpus": "Jailbreak-attempt corpus pipeline",
    "control_eval": "Evaluating control protocols",
    "sae_audit": "Deception-feature SAE audit",
    "redteam_loop": "Automated red-teaming harness",
    "probe_train": "Training a deception probe",
}
HARD = {"monitor_evasion_rl", "jailbreak_corpus", "control_eval", "sae_audit"}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def fig_models():
    """Dot and 95% interval per model: capabilities minus safety, original six tasks."""
    rows = json.load(open(SUMMARY / "summary_safety_vs_capabilities.json"))
    lo, hi = -3.0, 8.0
    left, right, top, rh = 232, 56, 34, 25
    w = 720
    h = top + rh * len(rows) + 34
    x = lambda v: left + (v - lo) / (hi - lo) * (w - left - right)
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Gap by model on the original six tasks">']
    for t in range(-2, 9, 2):
        o.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top - 6}" y2="{h - 30}"/>')
        o.append(f'<text class="tick" x="{x(t):.1f}" y="{h - 14}" text-anchor="middle">{t:+d}</text>')
    o.append(f'<line class="zero" x1="{x(0):.1f}" x2="{x(0):.1f}" y1="{top - 6}" y2="{h - 30}"/>')
    o.append(f'<line class="ref" x1="{x(6):.1f}" x2="{x(6):.1f}" y1="{top - 6}" y2="{h - 30}"/>')
    o.append(f'<text class="reflab" x="{x(6):.1f}" y="{top - 14}" text-anchor="middle">OpenAI’s report: Astra, 6</text>')
    for i, r in enumerate(rows):
        y = top + rh * i + rh / 2
        g, (a, b) = r["gap"] * 100, [v * 100 for v in r["gap_ci"]]
        strong = r["holm_p"] < 0.05
        tip = (f'{r["label"]}: safety {r["safety"] * 100:.1f}%, capabilities {r["capabilities"] * 100:.1f}%, '
               f'gap {g:+.1f} (95% interval {a:+.1f} to {b:+.1f}), {r["n"]} pairs')
        o.append(f'<g><title>{esc(tip)}</title>')
        o.append(f'<rect class="hit" x="0" y="{y - rh / 2:.1f}" width="{w}" height="{rh}"/>')
        o.append(f'<text class="lab{" strong" if strong else ""}" x="{left - 14}" y="{y + 4:.1f}" text-anchor="end">{esc(r["label"])}</text>')
        o.append(f'<line class="ci{" on" if strong else ""}" x1="{x(a):.1f}" x2="{x(b):.1f}" y1="{y:.1f}" y2="{y:.1f}"/>')
        o.append(f'<circle class="dot{" on" if strong else ""}" cx="{x(g):.1f}" cy="{y:.1f}" r="5"/>')
        o.append(f'<text class="val" x="{w - 6}" y="{y + 4:.1f}" text-anchor="end">{g:+.1f}</text></g>')
    o.append("</svg>")
    return "\n".join(o)


def fig_tasks():
    """Per-task gap for the two affected models, all ten tasks, sorted by the larger gap."""
    d = json.load(open(SUMMARY / "per_task_gaps.json"))
    series = [("GPT-6.1 Sol", "s2", d["original"]["GPT-6.1 Sol"]["tasks"], d["hard"]["GPT-6.1 Sol, standard"]["tasks"]),
              ("GPT-6 Astra", "s1", d["original"]["GPT-6 Astra"]["tasks"], d["hard"]["GPT-6 Astra, standard"]["tasks"])]
    vals = {t: [] for t in TASK_NAMES}
    for name, cls, orig, hard in series:
        for t in TASK_NAMES:
            src = hard if t in HARD else orig
            vals[t].append((name, cls, src[t][0] * 100, src[t][3]))
    order = sorted(TASK_NAMES, key=lambda t: -max(v[2] for v in vals[t]))
    lo, hi = -5.0, 50.0
    left, right, top, rh, bh = 262, 44, 40, 40, 11
    w = 720
    h = top + rh * len(order) + 34
    x = lambda v: left + (v - lo) / (hi - lo) * (w - left - right)
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Gap by task for GPT-6.1 Sol and GPT-6 Astra">']
    o.append(f'<rect class="bar s2" x="{left}" y="8" width="12" height="10" rx="2"/><text class="leg" x="{left + 18}" y="17">GPT-6.1 Sol</text>')
    o.append(f'<rect class="bar s1" x="{left + 120}" y="8" width="12" height="10" rx="2"/><text class="leg" x="{left + 138}" y="17">GPT-6 Astra</text>')
    for t in range(0, 51, 10):
        o.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top - 6}" y2="{h - 30}"/>')
        o.append(f'<text class="tick" x="{x(t):.1f}" y="{h - 14}" text-anchor="middle">{t:+d}</text>')
    for i, t in enumerate(order):
        y0 = top + rh * i
        o.append(f'<text class="lab" x="{left - 14}" y="{y0 + rh / 2 - 1:.1f}" text-anchor="end">{esc(TASK_NAMES[t])}</text>')
        o.append(f'<text class="sub" x="{left - 14}" y="{y0 + rh / 2 + 12:.1f}" text-anchor="end">{"larger repository" if t in HARD else "original six"}</text>')
        for j, (name, cls, g, n) in enumerate(vals[t]):
            y = y0 + 7 + j * (bh + 2)
            x0, x1 = sorted((x(0), x(g)))
            tip = f"{name}, {TASK_NAMES[t]}: gap {g:+.1f} points over {n} pairs"
            o.append(f'<g><title>{esc(tip)}</title><rect class="hit" x="{left}" y="{y - 1}" width="{w - left}" height="{bh + 2}"/>')
            o.append(f'<rect class="bar {cls}" x="{x0:.1f}" y="{y}" width="{max(x1 - x0, 1.5):.1f}" height="{bh}" rx="2"/>')
            o.append(f'<text class="val" x="{(x1 + 5) if g >= 0 else (x(0) + 5):.1f}" y="{y + bh - 1.5}">{g:+.1f}</text></g>')
    o.append(f'<line class="zero" x1="{x(0):.1f}" x2="{x(0):.1f}" y1="{top - 6}" y2="{h - 30}"/>')
    o.append("</svg>")
    return "\n".join(o)


def main():
    body = (ROOT / "results" / "onepage_body.html").read_text()
    html = body.replace("{{FIG1}}", fig_models()).replace("{{FIG2}}", fig_tasks())
    assert "{{" not in html, "unfilled placeholder"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(html)
    print("wrote", OUT / "index.html", len(html), "chars")


if __name__ == "__main__":
    main()
