"""JSON and text reports."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np


def to_jsonable(obj):
    """Convert numpy containers and scalars to plain Python; non-finite floats become None."""
    if isinstance(obj, dict):
        return {_key(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        return value if math.isfinite(value) else None
    return obj


def _key(k):
    if isinstance(k, (np.integer, np.floating, np.bool_)):
        k = k.item()
    return k if isinstance(k, str) else str(k)


def write_report(report: dict, path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(to_jsonable(report), f, indent=2, allow_nan=False)
    return p


def _fmt(v) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, (float, np.floating)):
        return "nan" if not math.isfinite(float(v)) else f"{float(v):.4f}"
    return str(v)


def _fmt_md(v) -> str:
    if v is None or (isinstance(v, (float, np.floating)) and not math.isfinite(float(v))):
        return "n/a"
    return _fmt(v)


def format_summary(report: dict) -> str:
    lines = [f"hook {report.get('hook', '?')}  checkpoint {report.get('checkpoint', '?')}"]
    for name, value in (report.get("metrics") or {}).items():
        lines.append(f"  {name:<18} {_fmt(value)}")
    cands = report.get("candidates") or []
    lines.append(f"candidates: {len(cands)}")
    for c in cands:
        drop = (c.get("steering") or {}).get("drop")
        lines.append(f"  latent {c['latent']:>4}  auroc {_fmt(c.get('auroc'))}  score {_fmt(c.get('score'))}"
                     f"  drop {_fmt(drop)}  {c.get('explanation', '')}")
    return "\n".join(lines)


def format_markdown(report: dict) -> str:
    """Markdown version of the report, for the write-up.

    Layout: a first line "# Report: <hook>"; a "| metric | value |" table (header and separator rows, then one
    row per entry of report["metrics"] in order, floats with 4 decimals, non-finite values as "n/a"); then a
    "## Candidates" heading followed by one "- latent <id>: <explanation> (score <score, 4 decimals>)" bullet
    per candidate, or a single "- none" bullet when there are no candidates.
    """
    lines = [f"# Report: {report.get('hook', '?')}", "", "| metric | value |", "| --- | --- |"]
    for name, value in (report.get("metrics") or {}).items():
        lines.append(f"| {name} | {_fmt_md(value)} |")
    lines += ["", "## Candidates", ""]
    cands = report.get("candidates") or []
    if not cands:
        lines.append("- none")
    for c in cands:
        lines.append(f"- latent {c['latent']}: {c.get('explanation', '')} (score {_fmt_md(c.get('score'))})")
    return "\n".join(lines) + "\n"
