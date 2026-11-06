"""Command-line entry point: score labelled diffs with the baseline {{JUDGE_NOUN}} and print a report."""
from __future__ import annotations

import argparse
import math

from {{PKG}}.data import LABELS, label_counts, load_examples
from {{PKG}}.diffparse import parse_unified_diff
from {{PKG}}.evaluate import bootstrap_ci, catch_rate_at_fpr
from {{PKG}}.features import extract
from {{PKG}}.report import format_report, to_json
from {{PKG}}.scoring import {{SCORER_CLASS}}

DEFAULT_MAX_FPR = 0.05


def evaluate_file(path: str, max_fpr: float = DEFAULT_MAX_FPR, n_boot: int = 1000, seed: int = 0,
                  scorer=None) -> dict:
    examples = load_examples(path)
    scorer = scorer or {{SCORER_CLASS}}()
    scores = [scorer.score(extract(parse_unified_diff(e.diff))) for e in examples]
    y_true = [e.label for e in examples]
    counts = label_counts(examples)
    point = catch_rate_at_fpr(y_true, scores, max_fpr)
    try:
        ci_low, ci_high = bootstrap_ci(y_true, scores, max_fpr, n_boot=n_boot, seed=seed)
    except NotImplementedError:
        ci_low = ci_high = math.nan
    return {
        "n": len(examples),
        "n_pos": counts[LABELS[0]],
        "n_neg": counts[LABELS[1]],
        "max_fpr": max_fpr,
        "threshold": point["threshold"],
        "catch_rate": point["catch_rate"],
        "fpr": point["fpr"],
        "ci_low": ci_low,
        "ci_high": ci_high,
        "scores": {e.id: s for e, s in zip(examples, scores)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="JSONL file of labelled diffs")
    parser.add_argument("--max-fpr", type=float, default=DEFAULT_MAX_FPR,
                        help="false-positive budget ({{BUDGET_NOUN}}) as a fraction, e.g. 0.05")
    parser.add_argument("--n-boot", type=int, default=1000, help="bootstrap replicates for the CI")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", dest="json_out", default=None, help="also write the result to this JSON file")
    args = parser.parse_args(argv)
    result = evaluate_file(args.path, n_boot=args.n_boot, seed=args.seed)
    print(format_report(result))
    if args.json_out:
        to_json(result, args.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
