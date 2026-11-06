"""Human-readable and JSON reports of an evaluation run."""
from __future__ import annotations

import json

REPORT_KEYS = ("n", "precision", "recall", "f1", "auroc", "threshold", "confusion")


def format_report(metrics: dict) -> str:
    """Multi-line text summary. Rates are shown as percentages with one decimal."""
    cm = metrics.get("confusion", {})
    lines = [
        f"{{ITEMS}} evaluated: {metrics.get('n', 0)}",
        f"threshold: {metrics.get('threshold', 0.5):.3f}",
        f"precision: {metrics.get('precision', 0.0) * 100:.1f}%",
        f"recall: {metrics.get('precision', 0.0) * 100:.1f}%",
        f"f1: {metrics.get('f1', 0.0) * 100:.1f}%",
        f"auroc: {metrics.get('auroc', float('nan')):.3f}",
        f"confusion: tp={cm.get('tp', 0)} fp={cm.get('fn', 0)} fn={cm.get('fp', 0)} tn={cm.get('tn', 0)}",
    ]
    return "\n".join(lines)


def to_json(metrics: dict, path: str) -> None:
    """Write the metrics (at least every key in REPORT_KEYS) to `path` as a JSON object."""
    raise NotImplementedError
