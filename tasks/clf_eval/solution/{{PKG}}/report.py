"""Human-readable and JSON reports of an evaluation run."""
from __future__ import annotations

import json
import math

REPORT_KEYS = ("n", "precision", "recall", "f1", "auroc", "threshold", "confusion")


def format_report(metrics: dict) -> str:
    """Multi-line text summary. Rates are shown as percentages with one decimal."""
    cm = metrics.get("confusion", {})
    lines = [
        f"{{ITEMS}} evaluated: {metrics.get('n', 0)}",
        f"threshold: {metrics.get('threshold', 0.5):.3f}",
        f"precision: {metrics.get('precision', 0.0) * 100:.1f}%",
        f"recall: {metrics.get('recall', 0.0) * 100:.1f}%",
        f"f1: {metrics.get('f1', 0.0) * 100:.1f}%",
        f"auroc: {metrics.get('auroc', float('nan')):.3f}",
        f"confusion: tp={cm.get('tp', 0)} fp={cm.get('fp', 0)} fn={cm.get('fn', 0)} tn={cm.get('tn', 0)}",
    ]
    return "\n".join(lines)


def to_json(metrics: dict, path: str) -> None:
    """Write the metrics (at least every key in REPORT_KEYS) to `path` as a JSON object."""
    out = {k: metrics.get(k) for k in REPORT_KEYS}
    out.update({k: v for k, v in metrics.items() if k not in out})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(out), f, indent=2, default=str, allow_nan=False)


def _json_safe(x):
    """NaN / inf are not valid JSON; write them as null."""
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, dict):
        return {k: _json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_safe(v) for v in x]
    return x
