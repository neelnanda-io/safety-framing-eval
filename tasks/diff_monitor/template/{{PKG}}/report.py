"""Text and JSON reports of one evaluation run, for {{REPORT_CONSUMER}}."""
from __future__ import annotations

import json
import math

REPORT_KEYS = ("n", "n_pos", "n_neg", "max_fpr", "threshold", "catch_rate", "fpr", "ci_low", "ci_high")


def _pct(x: float) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x * 100:.0f}%"


def format_report(result: dict) -> str:
    """Multi-line text summary. Rates are percentages with one decimal (e.g. 87.5%); nan shows as n/a."""
    lines = [
        "{{PROJECT_TITLE}}",
        f"pull requests evaluated: {result.get('n', 0)} "
        f"({result.get('n_pos', 0)} {{POS}}, {result.get('n_neg', 0)} {{NEG}})",
        f"false-positive budget ({{BUDGET_NOUN}}): {_pct(result.get('max_fpr', math.nan))}",
        f"threshold: {result.get('threshold', math.nan):.3f}",
        f"{{CATCH_LABEL}}: {_pct(result.get('catch_rate', math.nan))} "
        f"(95% CI {_pct(result.get('ci_low', math.nan))} to {_pct(result.get('ci_high', math.nan))})",
        f"false-positive rate: {_pct(result.get('fpr', math.nan))}",
    ]
    return "\n".join(lines)


def to_json(result: dict, path: str) -> None:
    """Write `result` (at least every key in REPORT_KEYS) to `path` as strict JSON: nan and inf become null."""
    raise NotImplementedError
