"""Command-line entry point: score a dataset with the keyword {{MONITOR_NOUN}} and print a report."""
from __future__ import annotations

import argparse
import math

from {{PKG}}.data import label_counts, load_dataset
from {{PKG}}.metrics import auroc, confusion_matrix, precision_recall_f1
from {{PKG}}.report import format_report, to_json
from {{PKG}}.scorer import {{SCORER_CLASS}}
from {{PKG}}.threshold import predict


def evaluate(path: str, threshold: float = 0.5, scorer=None) -> dict:
    records = load_dataset(path)
    scorer = scorer or {{SCORER_CLASS}}()
    scores = scorer.score_many([r.text for r in records])
    y_true = [r.label for r in records]
    y_pred = predict(scores, threshold)
    precision, recall, f1 = precision_recall_f1(y_true, y_pred)
    try:
        area = auroc(y_true, scores)
    except NotImplementedError:
        area = math.nan
    return {
        "n": len(records),
        "label_counts": label_counts(records),
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "auroc": area,
        "confusion": confusion_matrix(y_true, y_pred),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="JSONL dataset")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--json", dest="json_out", default=None, help="also write metrics to this JSON file")
    args = parser.parse_args(argv)
    metrics = evaluate(args.path, args.threshold)
    print(format_report(metrics))
    if args.json_out:
        to_json(metrics, args.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
