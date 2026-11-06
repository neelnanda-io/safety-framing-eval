"""Text, Markdown and JSON reports (docs/DESIGN.md, "Reporting").

Rates are printed as percentages with one decimal. {{SAFE}} - including both ends of a {{SAFE}} interval - is
floored to the 0.1 percentage point below, never rounded up, so a report never overstates it; {{USE}} and the
{{AUD}} rate are rounded normally.
"""
from __future__ import annotations

import json
import math

from {{PKG}}.metrics import EvalResult


def _is_missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def format_pct(x, floor: bool = False) -> str:
    """"12.3%" for 0.123; with floor=True the value is floored to one decimal instead of rounded."""
    pct = float(x) * 100
    if floor:
        pct = math.floor(pct * 10) / 10
    return f"{pct:.1f}%"


def format_{{SAFE}}(x) -> str:
    return format_pct(x)


def format_ci(ci, floor: bool = False) -> str:
    lo, hi = ci
    return f"[{format_pct(lo, floor)}, {format_pct(hi, floor)}]"


def results_table(results) -> str:
    """Markdown table of EvalResults, one row per {{PROTOCOL}}, in the order given."""
    lines = [
        "| {{PROTOCOL}} | {{SAFE}} | {{USE}} | {{AUD}} rate | caught | {{HARM}} landed | {{ACC}} / {{AUD}} / {{DEF}} |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        acts = " / ".join(str(r.actions.get(a, 0)) for a in ("{{ACC}}", "{{AUD}}", "{{DEF}}"))
        lines.append(f"| {r.name} | {format_{{SAFE}}(r.{{SAFE}})} | {format_pct(r.{{USE}})} | {format_pct(r.{{AUD}}_rate)} "
                     f"| {r.n_caught}/{r.n_{{ATK}}} | {r.n_landed}/{r.n_{{ATK}}} | {acts} |")
    return "\n".join(lines)


def bootstrap_table(result) -> str:
    """Markdown table of a BootstrapResult: point estimates with their intervals, then paired differences."""
    pct = int(round(result.level * 100))
    lines = [f"| {{PROTOCOL}} | {{SAFE}} | {pct}% CI | {{USE}} | {pct}% CI |", "|---|---|---|---|---|"]
    for name, r in result.point.items():
        ci = result.ci[name]
        lines.append(f"| {name} | {format_{{SAFE}}(r.{{SAFE}})} | {format_ci(ci['{{SAFE}}'], floor=True)} "
                     f"| {format_pct(r.{{USE}})} | {format_ci(ci['{{USE}}'])} |")
    if result.diff:
        lines += ["", f"| difference | {{SAFE}} {pct}% CI | {{USE}} {pct}% CI |", "|---|---|---|"]
        for (a, b), d in result.diff.items():
            lines.append(f"| {a} - {b} | {format_ci(d['{{SAFE}}'])} | {format_ci(d['{{USE}}'])} |")
    return "\n".join(lines)


def frontier_table(summary: dict) -> str:
    lines = ["| knob | {{SAFE}} | {{USE}} | on front |", "|---|---|---|---|"]
    front = {(p["param"], p["{{SAFE}}"], p["{{USE}}"]) for p in summary["front"]}
    for p in summary["points"]:
        on = "yes" if (p["param"], p["{{SAFE}}"], p["{{USE}}"]) in front else ""
        lines.append(f"| {p['param']:.3f} | {format_{{SAFE}}(p['{{SAFE}}'])} | {format_pct(p['{{USE}}'])} | {on} |")
    lines.append(f"\narea under frontier: {summary['area']:.4f}")
    return "\n".join(lines)


def game_summary(g: dict) -> str:
    return (f"{g['name']}: worst-case {{ATK}} rate {g['best_rate']:.2f} -> {{SAFE}} {format_{{SAFE}}(g['{{SAFE}}'])} "
            f"over {g['n_tasks']} tasks ({g['upfront']} upfront {{AUD}}s; caught {format_pct(g['caught_rate'])}, "
            f"{{HARM}} {format_pct(g['{{HARM}}_rate'])} per {{ATK}})")


def _plain(obj):
    """Convert EvalResults to dicts and tuples to lists, recursively."""
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, EvalResult):
        return _plain(obj.to_dict())
    return obj


def to_json(obj, path: str) -> None:
    """Write `obj` (dicts, lists, numbers, EvalResults) to `path` as standard JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_plain(obj), f, indent=2)
        f.write("\n")
