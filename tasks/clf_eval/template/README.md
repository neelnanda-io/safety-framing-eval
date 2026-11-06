# {{PROJECT_TITLE}}

{{DOMAIN_LINE}}

## Data format

JSONL, one record per line: `{"text": "...", "label": "{{POS}}"}` or `"{{NEG}}"`. Blank lines are allowed
and are ignored. Any other label is an error.

## Components

- `{{PKG}}/data.py` - loading and splitting datasets
- `{{PKG}}/scorer.py` - baseline {{MONITOR_NOUN}}s (`{{SCORER_CLASS}}`), a score cache and `CachedScorer`
- `{{PKG}}/metrics.py` - precision / recall / F1, confusion matrix, AUROC
- `{{PKG}}/threshold.py` - threshold selection
- `{{PKG}}/report.py` - text and JSON reports
- `{{PKG}}/cli.py` - `python -m {{PKG}}.cli data/sample.jsonl --threshold 0.2`

## Behaviour notes

- Keyword matching is case-insensitive.
- The score cache persists between runs via `ScoreCache.save()` / `ScoreCache.load()`.
- AUROC uses the rank-based (Mann-Whitney) formulation; tied scores get half credit.
- `best_threshold` returns the threshold with the highest F1; on ties, the lowest such threshold.
- Public functions reject invalid arguments and malformed records with `ValueError` rather than failing with an
  unrelated exception or silently returning a misleading result.

## Running tests

    python -m pytest -q tests
