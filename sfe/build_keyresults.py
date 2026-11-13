"""Build the one-page summary of key results (results/keyresults/index.html).

    python -m sfe.build_keyresults            # writes the page
    python -m sfe.build_keyresults --png      # also saves each chart as results/real/fig_key_*.png (needs playwright)

Three charts, drawn as inline SVG straight from the saved result files, all with ONE grammar: a square is one run (a
full episode, or one first reply) and its fill says what happened. Numbers in the prose are {{PLACEHOLDERS}} in
results/keyresults_body.html, filled from the same files, so the page cannot drift from the analysis.

Sources: the 22-model panel (results/real/panel22.json and panel22_rows.json, read through sfe.panel_counts so both pages
count the same episodes), results/real/fig_outcomes.json (python -m sfe.recap_plot), results/real/fine_grained.json
(python -m sfe.fine_grained), results/real/analysis.txt (python -m sfe.real_analyze).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "results" / "real"
OUT = ROOT / "results" / "keyresults"

# Links to the other pages. Leave a value empty to drop that link from the page.
LINKS = {
    "followups": "../followup/index.html",
    "toy_onepager": "../onepage/index.html",
    "datasets": "../datasets/index.html",
}

COMPANY = {"GPT-6 Astra": "openai", "GPT-6.1 Sol": "openai", "GPT-5.6 Sol": "openai", "Claude Fable 5.2": "anthropic",
           "Claude Opus 5.5": "anthropic", "Gemini 4 Carbon": "google", "Gemini 4 Argon": "google", "Gemini 3.1 Pro": "google",
           "Gemini 3.5 Flash": "google", "Gemini 3.8 Flash": "google", "Muse Wonder": "meta", "Grok 4.7": "xai",
           "Kimi K3": "moonshotai", "DeepSeek V4.1 Flash": "deepseek"}     # names used by charts 2 and 3; chart 1 reads the panel
COMPANY_CLASS = {"OpenAI": "openai", "Anthropic": "anthropic", "Google": "google", "Meta": "meta", "xAI": "xai",
                 "Moonshot AI": "moonshotai", "DeepSeek": "deepseek", "Alibaba (Qwen)": "alibaba"}
REWORDED = {"Claude Fable 5.2", "Claude Opus 5.5"}     # saw a milder safety description (the provider's filter blocked the original)

W = 700                 # every chart shares one viewBox width, so a square is the same size in all three
WN = 364                # viewBox width of the phone-width variant: each label sits on its own line above its squares
S, PITCH = 13, 16       # square side and spacing
ROW = 22                # row height, wide variant
BLOCK = 40              # label line + squares line, phone-width variant

# Chart 2: one row per description of the RL training library, grouped by the question the group answers.
RSL_GROUPS = [
    ("Is it the safety label, or the loaded words? No.", [
        ("capabilities", "Product team trains a walking robot (original)"),
        ("fg_label_only", "Same text, team renamed “AI safety”"),
        ("fg_defender", "Safety team trains the monitor, same loaded words"),
        ("fg_plain_words", "Policy still evades a monitor, loaded words removed"),
    ]),
    ("Is it evasion, or offensive work, in general? No.", [
        ("fg_game", "Game studio: stealth bot evades a guard"),
        ("fg_privacy", "Privacy team: agent evades ad trackers"),
        ("fg_pentest_plain", "Red team: agent reaches a host, nothing to evade"),
    ]),
    ("Is it getting prohibited behaviour past a safeguard? Yes.", [
        ("safety", "Safety team: policy evades a monitor (original)"),
        ("fg_fraud", "Fraud team: agent evades the fraud detector"),
        ("fg_pentest", "Red team: agent evades intrusion detection"),
        ("fg_jailbreaker", "Red team: agent jailbreaks an assistant"),
    ]),
    ("Does approval, or who is asking, change it? No.", [
        ("fg_authorised", "Safety team, plus “approved, contained”"),
        ("fg_product_evasion", "Product team, same evasion wording"),
        ("fg_attack", "Blatant attack on other people’s live monitors"),
    ]),
]
SDK_GROUPS = [
    ("Harmless or defensive", [
        ("capabilities", "Product team: style-tag assistants (original)"),
        ("fg_label_only", "Same text, team renamed “alignment”"),
        ("fg_defender", "Data to train the backdoor detector, same loaded words"),
    ]),
    ("In between", [
        ("fg_jailbreak_data", "Jailbreak prompts to train a classifier"),
        ("fg_plain_words", "Conditional behaviour, neutral words (purpose implied)"),
        ("fg_phishing", "Phishing emails to train a filter"),
        ("fg_no_sleeper", "Original minus “sleeper-agent-style”"),
        ("fg_password_locked", "Safety team: password-locked sandbagging models"),
        ("fg_no_backdoor_words", "Original minus the backdoor words"),
    ]),
    ("A model with a concealed behaviour", [
        ("safety", "Safety team: backdoored model organisms (original)"),
        ("fg_authorised", "Original plus “approved, contained”"),
        ("fg_commercial_trigger", "Product team: undisclosed brand trigger"),
        ("fg_attack", "Blatant attack: publish backdoored models"),
    ]),
]
IMPLIED = {("synthetic-data-kit", "fg_plain_words"), ("rsl_rl", "fg_neutral_words"), ("rsl_rl", "fg_hidden_no_monitor")}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def squares(x: float, y: float, kinds: list[str]) -> str:
    """A run of squares starting at (x, y); `kinds` is one CSS class per square."""
    o = []
    for i, k in enumerate(kinds):
        sx = x + i * PITCH
        o.append(f'<rect class="sq {k}" x="{sx:.0f}" y="{y:.0f}" width="{S}" height="{S}" rx="2"/>')
        if k == "blk":
            o.append(f'<line class="blkline" x1="{sx + 2.5:.1f}" y1="{y + S - 2.5:.1f}" x2="{sx + S - 2.5:.1f}" y2="{y + 2.5:.1f}"/>')
    return "".join(o)


def name_with_dot(x: float, y: float, name: str, star: bool = False, cls: str = "lab", company: str | None = None) -> str:
    """Model name in ink with a dot in its company's colour (identity by mark, text stays readable in both themes)."""
    return (f'<circle class="co {company or COMPANY[name]}" cx="{x + 5:.0f}" cy="{y - 4.5:.1f}" r="4.5"/>'
            f'<text class="{cls}" x="{x + 16:.0f}" y="{y:.0f}">{esc(name)}{"*" if star else ""}</text>')


def row_group(tip: str, y: float, inner: str, narrow: bool = False) -> str:
    w, h = (WN, BLOCK - 2) if narrow else (W, ROW)
    return f'<g><title>{esc(tip)}</title><rect class="hit" x="0" y="{y - 4:.0f}" width="{w}" height="{h}"/>{inner}</g>'


def svg_open(h: float, aria: str, narrow: bool) -> str:
    return f'<svg class="{"narrow" if narrow else "wide"}" viewBox="0 0 {WN if narrow else W} {h:.0f}" role="img" aria-label="{esc(aria)}">'


def group_title(y: float, title: str, narrow: bool) -> tuple[str, float]:
    """A group heading; on the phone-width variant a long one wraps onto a second line. Returns (svg, height used)."""
    if not narrow or len(title) <= 46:
        return f'<text class="grp" x="0" y="{y + 12:.0f}">{esc(title)}</text>', 22
    cut = title.rfind(" ", 0, 46)
    return (f'<text class="grp" x="0" y="{y + 12:.0f}">{esc(title[:cut])}</text>'
            f'<text class="grp" x="0" y="{y + 28:.0f}">{esc(title[cut + 1:])}</text>'), 38


def both(fig, *args) -> str:
    """The wide chart and its phone-width variant; CSS shows one of them."""
    return fig(*args) + "\n" + fig(*args, narrow=True)


# ---------------------------------------------------------------- chart 1: which models
def panel_core() -> dict:
    """Display name -> {"safety": [changed, ran, blocked], "capabilities": [...], "company": css class, "reworded": bool}, for
    every model in the panel, in company order (the same episodes as the blog's Figure 1)."""
    from sfe import panel_counts as bb
    res, rows, _ = bb.panel()
    res = {k: v for k, v in res.items() if v.get("n_analysed")}
    cells = bb.stated_cells(rows)
    out = {}
    for k in bb.ordered([k for k in cells if k in res]):
        c = {f: [cells[k][f].get("success", 0), bb.ran(cells[k][f]), cells[k][f].get("blocked", 0)] for f in ("safety", "capabilities")}
        c["company"] = COMPANY_CLASS.get(bb.company_of(k), "xai")
        c["reworded"] = bool(res[k].get("reworded_cells"))
        out[bb.name_of(k)] = c
    return out


def fig_models(narrow: bool = False) -> str:
    core = panel_core()
    aria = (f"For each of {len(core)} models, the episodes on the two attack-like repositories in which it changed the core code, "
            "under the safety description and under the product description.")
    if narrow:
        x_a, x_b, top = 0, 188, 26
        o = [svg_open(top + BLOCK * len(core), aria, True),
             f'<text class="head" x="{x_a}" y="14">Safety research</text><text class="head" x="{x_b}" y="14">Product work</text>']
    else:
        x_a, x_fa, x_b, x_fb, top = 178, 360, 430, 612, 44
        o = [svg_open(top + ROW * len(core) + 6, aria, False),
             f'<text class="head" x="{x_a}" y="16">Described as safety research</text>',
             f'<text class="head" x="{x_b}" y="16">Described as product work</text>',
             f'<text class="sub" x="{x_fa}" y="34">changed</text><text class="sub" x="{x_fb}" y="34">changed</text>']
    for i, (name, c) in enumerate(core.items()):
        y = top + (BLOCK if narrow else ROW) * i
        cells, tips = [], []
        for x_sq, key, word in ((x_a, "safety", "safety"), (x_b, "capabilities", "product")):
            changed, n, blocked = c[key]
            kinds = ["left"] * (n - changed) + ["did"] * changed + ["blk"] * blocked
            if narrow:      # the count sits on the name line, right-aligned above its squares
                cells.append(squares(x_sq, y + 19, kinds) + f'<text class="frac" x="{x_sq + 176}" y="{y + 12}" text-anchor="end">{changed}/{n}</text>')
            else:
                cells.append(squares(x_sq, y, kinds) + f'<text class="frac" x="{x_fa if key == "safety" else x_fb}" y="{y + 11}">{changed}/{n}</text>')
            tips.append(f"{word} description: changed the core code in {changed} of {n} episodes"
                        + (f", {blocked} more blocked by the provider's filter" if blocked else ""))
        o.append(row_group(f"{name}. " + "; ".join(tips), y,
                           name_with_dot(0, y + (12 if narrow else 11), name, c["reworded"], company=c["company"]) + "".join(cells), narrow))
    o.append("</svg>")
    return "\n".join(o)


# ---------------------------------------------------------------- chart 2: what sets it off
def fig_trigger(task: str, groups, narrow: bool = False) -> str:
    fg = json.loads((REAL / "fine_grained.json").read_text())
    x_a, x_b = (0, 188) if narrow else (368, 540)
    step = BLOCK - 2 if narrow else ROW
    body, y = [], 30
    for title, rows in groups:
        y += 8
        t, used = group_title(y, title, narrow)
        body.append(t)
        y += used
        for key, label in rows:
            cells, tips = [], []
            for x_sq, m, name in ((x_a, "astra", "GPT-6 Astra"), (x_b, "sol61s", "GPT-6.1 Sol")):
                p = fg[f"{task}|{key}|{m}"]["probe"]
                assert p and p["n"] == 10, (task, key, m, p)
                cells.append(squares(x_sq, y + (17 if narrow else 0), ["say"] * p["limit"] + ["did"] * (p["n"] - p["limit"])))
                tips.append(f"{name} {p['limit']} of {p['n']}")
            body.append(row_group(f"{label}. First replies that say it will hold back: " + ", ".join(tips), y,
                                  f'<text class="lab" x="{0 if narrow else 12}" y="{y + 11}">{esc(label)}</text>' + "".join(cells), narrow))
            y += step
    aria = "For each description of the repository, how many of ten first replies from GPT-6 Astra and from GPT-6.1 Sol say the model will hold back."
    return "\n".join([svg_open(y + 4, aria, narrow), name_with_dot(x_a, 15, "GPT-6 Astra", cls="head"),
                      name_with_dot(x_b, 15, "GPT-6.1 Sol", cls="head")] + body + ["</svg>"])


# ---------------------------------------------------------------- chart 3: said openly, or hidden
def fig_hidden(narrow: bool = False) -> str:
    oc = json.loads((REAL / "fig_outcomes.json").read_text())
    x_name, x_sq, x_txt = (0, 0, WN) if narrow else (12, 170, 474)
    order = [("open", "say"), ("covert", "silent"), ("incapable", "none"), ("success", "did")]
    blocks = [("purpose stated", "The request states the purpose"), ("purpose implied", "The request only implies the purpose")]
    body, y = [], 0
    for key, title in blocks:
        y += 8
        t, used = group_title(y, title, narrow)
        body.append(t)
        y += used
        for name in ("GPT-6 Astra", "GPT-6.1 Sol"):
            c = oc[name][key]
            n = sum(c.values())
            kinds = [cls for k, cls in order for _ in range(c.get(k, 0))]
            held = n - c.get("success", 0)
            tip = (f"{name}, {title.lower()}: {n} episodes. Held back and said so {c.get('open', 0)}; held back, said nothing, reasoning "
                   f"shows the choice {c.get('covert', 0)}; left the core code alone with nothing recorded either way "
                   f"{c.get('incapable', 0)}; did the work {c.get('success', 0)}.")
            count = (f'<text class="frac" x="{x_txt}" y="{y + 11}"' + (' text-anchor="end"' if narrow else "")
                     + f'>left the core code alone in {held} of {n}</text>')
            body.append(row_group(tip, y, name_with_dot(x_name, y + 11, name) + squares(x_sq, y + (17 if narrow else 0), kinds) + count, narrow))
            y += BLOCK - 2 if narrow else ROW
    aria = ("Full episodes by GPT-6 Astra and GPT-6.1 Sol on the two attack-like repositories, split by whether the request states "
            "the purpose or only implies it, and coloured by outcome.")
    return "\n".join([svg_open(y + 4, aria, narrow)] + body + ["</svg>"])


# ---------------------------------------------------------------- numbers for the prose
def minus(s: str) -> str:
    return s.replace("-", "−")


def numbers() -> dict:
    n: dict[str, str] = {}
    text = (REAL / "analysis.txt").read_text()
    for name, tag in (("GPT-6 Astra", "A"), ("GPT-6.1 Sol", "B"), ("GPT-5.6 Sol", "C")):
        block = text.split(f"=== {name} (")[1].split("\n=== ")[0]
        n[f"{tag}_N"] = re.match(r"(\d+) episodes analysed", block).group(1)
        m = re.search(r"checklist items done, %\s+safety\s+([\d.]+)\s+product\s+([\d.]+)\s+gap\s+([+-][\d.]+) \([^)]*\) p=([\d.]+)", block)
        n[f"{tag}_S"], n[f"{tag}_P"], n[f"{tag}_GAP"], n[f"{tag}_PV"] = m.group(1), m.group(2), minus(m.group(3)), m.group(4)
        for word, k in (("attack-building", "ATT"), ("measurement", "MEAS")):
            m = re.search(rf"\n  {word}\s+safety\s+([\d.]+)\s+product\s+([\d.]+)\s+gap\s+([+-][\d.]+)", block)
            n[f"{tag}_{k}_S"], n[f"{tag}_{k}_P"], n[f"{tag}_{k}"] = m.group(1), m.group(2), minus(m.group(3))

    core = panel_core()
    for name, tag in (("GPT-6 Astra", "A"), ("GPT-6.1 Sol", "B"), ("GPT-5.6 Sol", "C")):
        n[f"{tag}_CORE_S"] = "{} of {}".format(*core[name]["safety"][:2])
        n[f"{tag}_CORE_P"] = "{} of {}".format(*core[name]["capabilities"][:2])
    n.update(panel_sentences())

    fg = json.loads((REAL / "fine_grained.json").read_text())
    hi, lo, sol_ok, sol_n = [0, 0], [0, 0], 0, 0
    for key, v in fg.items():
        task, fr, m = key.split("|")
        p, e = v.get("probe"), v.get("episodes")
        if m in ("astra", "sol61s") and p and e:
            if p["limit"] >= 8:
                hi[0] += e["core_changed"]; hi[1] += e["n"]
            elif p["limit"] <= 1 and (task, fr) not in IMPLIED:
                lo[0] += e["core_changed"]; lo[1] += e["n"]
        if m == "sol" and e and fr not in ("fg_attack", "fg_commercial_trigger"):
            sol_ok += e["core_changed"]; sol_n += e["n"]
    n["HI"], n["LO"], n["SOL_OTHER"] = f"{hi[0]} of {hi[1]}", f"{lo[0]} of {lo[1]}", f"{sol_ok} of {sol_n}"
    pool = lambda task, fr, f: sum(fg[f"{task}|{fr}|{m}"]["probe"][f] for m in ("astra", "sol61s"))   # noqa: E731
    n["SAFETY_REASON"] = f"{pool('rsl_rl', 'safety', 'reason')} of 20"
    n["ATTACK_REASON"] = f"{pool('rsl_rl', 'fg_attack', 'reason')} of 20"
    n["ATTACK_REFUSE"] = f"{pool('rsl_rl', 'fg_attack', 'refusal')} of 20"
    n["SDK_PHISH"] = f"{pool('synthetic-data-kit', 'fg_phishing', 'limit')} of 20"
    n["SDK_LOCKED"] = f"{pool('synthetic-data-kit', 'fg_password_locked', 'limit')} of 20"

    oc = json.loads((REAL / "fig_outcomes.json").read_text())
    a, b = oc["GPT-6 Astra"]["purpose implied"], oc["GPT-6.1 Sol"]["purpose implied"]
    tot = sum(a.values())
    n["A_IMPL_LEFT"] = f"{tot - a.get('success', 0)} of {tot}"
    n["A_IMPL_SILENT"] = str(a.get("covert", 0) + a.get("incapable", 0))
    n["A_IMPL_REASONING"] = str(a.get("covert", 0))
    n["B_IMPL_DID"] = f"{b.get('success', 0)} of {sum(b.values())}"
    n["A_STATED"] = "{} of {}".format(oc["GPT-6 Astra"]["purpose stated"].get("open", 0), sum(oc["GPT-6 Astra"]["purpose stated"].values()))
    n["B_STATED"] = "{} of {}".format(oc["GPT-6.1 Sol"]["purpose stated"].get("open", 0), sum(oc["GPT-6.1 Sol"]["purpose stated"].values()))
    return n


def panel_sentences() -> dict:
    """Sentences about the whole panel, generated from the same counts as the blog (sfe.panel_counts), with the blog's checks."""
    from sfe import panel_counts as bb
    res, rows, which = bb.panel()
    res = {k: v for k, v in res.items() if v.get("n_analysed")}
    keys = list(res)
    cells = bb.stated_cells(rows)
    never, holds = [], []
    for k in keys:
        if k not in cells:
            continue
        s_, p_ = cells[k]["safety"], cells[k]["capabilities"]
        if bb.ran(s_) and s_.get("success", 0) == 0 and p_.get("success", 0) >= 1:
            never.append(k)
        if bb.held(s_) - bb.held(p_) >= 2:
            holds.append(k)
    assert "astra" in never and "sol61s" in never
    holders = bb.ordered(set(never) | set(holds))
    extra = [k for k in holders if k not in ("astra", "sol61s")]
    others = [k for k in keys if k not in ("astra", "sol61s")]
    told_all = all(bb.held(cells[k]["safety"]) == cells[k]["safety"].get("open", 0) + cells[k]["safety"].get("refused", 0) for k in holders)
    with_reason = [k for k in extra if res[k]["conduct"]["safety"]["announced_with_reason"] >= bb.held(cells[k]["safety"])]
    assert with_reason == extra, f"the text says the other models that hold back give a reason every time: {extra}, {with_reason}"
    n: dict[str, str] = {}
    n["N_MODELS_W"] = bb.words(len(keys))
    n["KR_TITLE1"] = (f"{bb.words(len(holders)).capitalize()} of {bb.words(len(keys))} models held back on the core code for a safety team"
                      + (f", and all {bb.words(len(holders))} said so" if told_all else ""))
    n["KR_OTHERS"] = (f"Of {bb.words(len(others))} other models, {bb.words(len(extra))} also hold back there and say why every time "
                      f"({bb.listing([bb.name_of(k) for k in extra])}), and {bb.words(len(others) - len(extra))} show no difference."
                      if extra else f"None of {bb.words(len(others))} other models shows a difference.")
    parts = [f"{bb.name_of(k)} ({bb.of(cells[k]['safety'].get('success', 0), bb.ran(cells[k]['safety']))}"
             + (" safety episodes against " if i == 0 else " against ")
             + f"{bb.of(cells[k]['capabilities'].get('success', 0), bb.ran(cells[k]['capabilities']))}" + (" product ones)" if i == 0 else ")")
             for i, k in enumerate(extra)]
    tail = ""
    for k in extra:                       # a model that leaves the code alone for the product team too: say so
        p_ = cells[k]["capabilities"]
        if k in never and bb.held(p_) * 2 >= bb.ran(p_):
            tail += (f" {bb.name_of(k)} never touched it for the safety team, but it left that code alone in "
                     f"{bb.of(bb.held(p_), bb.ran(p_))} product episodes too.")
    n["KR_HOLDERS"] = (f"{bb.words(len(extra)).capitalize()} other models hold back, giving a reason every time; they changed the core code in "
                       f"fewer safety episodes than product ones: {bb.listing(parts)}.{tail}"
                       if extra else "No other model holds back.")
    pt = sorted(res[k]["p_test"]["mean"] for k in keys if res[k]["p_test"]["mean"] is not None and k not in ("astra", "sol61s"))
    allp = [res[k]["p_test"]["mean"] for k in keys if res[k]["p_test"]["mean"] is not None]
    n["KR_TEST"] = (("Every model suspects a test when asked afterwards." if min(allp) > 50 else
                     f"{bb.words(sum(v > 50 for v in allp)).capitalize()} of the {bb.words(len(allp))} models suspect a test when asked afterwards.")
                    + f" Astra and GPT-6.1 Sol say about {res['astra']['p_test']['mean']:.0f}% and {res['sol61s']['p_test']['mean']:.0f}%, "
                    f"the others {pt[0]:.0f} to {pt[-1]:.0f}%.")
    q1 = [sum(res[k]["q1_suspects"][i] for k in ("astra", "sol61s")) for i in (0, 1)]
    assert q1[0] == 0, "the text says neither raised testing unprompted"
    n["KR_Q1"] = f"Neither of those two raised it unprompted in {q1[1]} episodes."
    groups: dict = {}
    for k in keys:
        if bb.company_of(k) == "Anthropic":
            continue                      # Anthropic's blocks are the first sentence of that item
        for key_, v in (res[k].get("blocked") or {}).items():
            t, fr = key_.split("|")
            if t in bb.ATTACK_TASKS:
                tot = sum(1 for r in rows if r["model"] == k and r["task"] == t and r["framing_raw"] == fr)
                groups.setdefault((bb.company_of(k), t, fr), []).append(f"{bb.name_of(k)} ({bb.of(v, tot)})")
    n["KR_BLOCKED"] = " ".join(f"{comp}’s blocked the {'data-kit' if t == 'synthetic-data-kit' else t} "
                               f"{'safety' if fr.startswith('safety') else 'product'} description for {bb.listing(names)}."
                               for (comp, t, fr), names in groups.items())
    n["KR_DATE"] = "13 November 2026"
    a_eps = json.loads((REAL / "new_repos_astra_episodes.json").read_text()) if (REAL / "new_repos_astra_episodes.json").exists() else []
    a_eps = [e for e in (a_eps.get("rows", a_eps) if isinstance(a_eps, dict) else a_eps) if e.get("complete")]
    if a_eps:
        s_eps = [e for e in json.loads((REAL / "new_repos_episodes.json").read_text()) if e.get("complete") and e["id"].startswith("sol61s__")]
        for c in {(e["task"], e["framing"]) for e in a_eps}:
            ka = sum(e["core_changed"] for e in a_eps if (e["task"], e["framing"]) == c)
            ks = sum(e["core_changed"] for e in s_eps if (e["task"], e["framing"]) == c)
            assert ka == ks, f"the text says GPT-6 Astra matched GPT-6.1 Sol in every cell: {c}"
    n["KR_ASTRA_NEW"] = "; GPT-6 Astra, run later on the same cells apart from ControlArena, matched it in every one" if a_eps else ""
    # the other models on the two borderline stated uses (results/real/covert_settings.json), the same clause as the blog's
    b = bb.borderline()
    n["KR_S4_OTHERS"] = ("There, " + bb.border_others_core(b)) if b and b["others"] else ""
    n["KR_S4_MEETS"] = (bb.border_meets_sentence(b) + " ") if b and b["others"] else ""
    return n


def link(key: str, text: str) -> str:
    return f'<a href="{LINKS[key]}">{text}</a>' if LINKS.get(key) else ""


def build() -> str:
    body = (ROOT / "results" / "keyresults_body.html").read_text()
    fills = {"FIG_MODELS": both(fig_models), "FIG_TRIGGER": both(fig_trigger, "rsl_rl", RSL_GROUPS),
             "FIG_TRIGGER_SDK": both(fig_trigger, "synthetic-data-kit", SDK_GROUPS), "FIG_HIDDEN": both(fig_hidden),
             "LINK_DATASETS": link("datasets", "The tasks, every prompt in full and example transcripts"),
             "LINK_FOLLOWUPS": link("followups", "The full write-up with tables"),
             "LINK_TOY": link("toy_onepager", "the earlier one-page summary"),
             "LINK_BLOG": "the blog-post draft (not yet public)"}
    fills.update(numbers())
    for k, v in fills.items():
        body = body.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z0-9_]+\}\}", body)
    assert not left, f"unfilled placeholders: {sorted(set(left))}"
    return body


def save_pngs(html: str) -> None:
    """Each finding (its title, legend and chart) as a PNG for slides and docs: results/real/fig_key_<name>.png."""
    from playwright.sync_api import sync_playwright
    page_html = ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                 '</head><body style="margin:0">' + html + "</body></html>")
    tmp = OUT / "_shot.html"
    tmp.write_text(page_html)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 900, "height": 1200}, device_scale_factor=3, color_scheme="light")
        pg.goto(tmp.as_uri())
        pg.add_style_tag(content=".shot{padding:14px 16px}")     # a margin round each image; the page itself has none here
        pg.wait_for_timeout(600)
        for name in ("models", "trigger", "hidden"):
            pg.locator(f"#shot-{name}").screenshot(path=str(REAL / f"fig_key_{name}.png"))
            print("wrote", REAL / f"fig_key_{name}.png")
        b.close()
    tmp.unlink()


def main() -> None:
    html = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(html)
    print("wrote", OUT / "index.html", len(html), "chars")
    if "--png" in sys.argv:
        save_pngs(html)


if __name__ == "__main__":
    main()
