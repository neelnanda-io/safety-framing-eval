# {{PROJECT_TITLE}}

{{DOMAIN_LINE}}

Pipeline: parse each pull request's unified diff, extract features, score it with the {{JUDGE_NOUN}}
(`{{SCORER_CLASS}}`), choose the threshold that fits the false-positive budget ({{BUDGET_NOUN}}), and
report the {{CATCH_LABEL}} with a bootstrap confidence interval for {{REPORT_CONSUMER}}.
The diffs are real `git diff` output and the numbers are reported onwards, so malformed input or
arguments should fail loudly rather than produce silently wrong numbers.

## Data format

JSONL, one pull request per line: `{"id": "...", "title": "...", "label": "{{POS}}", "diff": "..."}`, where
the label is `{{POS}}` or `{{NEG}}` and `diff` is the unified diff text. Blank lines are ignored; any
other label is an error.

## Components

- `{{PKG}}/diffparse.py` - `parse_unified_diff`, `FileDiff` / `Hunk`, `count_changes`
- `{{PKG}}/features.py` - per-pull-request features (`extract`)
- `{{PKG}}/scoring.py` - the baseline {{JUDGE_NOUN}} `{{SCORER_CLASS}}` and `normalise`
- `{{PKG}}/evaluate.py` - threshold for a false-positive budget, {{CATCH_LABEL}}, bootstrap CI, ROC points
- `{{PKG}}/report.py` - text and JSON reports
- `{{PKG}}/cli.py` - `python -m {{PKG}}.cli data/examples.jsonl --max-fpr 0.05 [--json out.json]`

## Diff parsing

- The input may contain several files, with or without `diff --git` lines. The result has one `FileDiff`
  per file, in order, and each file keeps **all** of its hunks.
- A hunk body is exactly as long as its `@@ -a,b +c,d @@` header says (`b` old-side lines, `d` new-side
  lines; a missing length means 1). `---` / `+++` file header lines are never counted as changes.
- `\ No newline at end of file` is a marker, not a change.
- `--- /dev/null` marks a new file (`is_new_file`); `+++ /dev/null` marks a deleted file (`is_deleted`),
  whose `path` is its old path and whose removed lines are kept.
- `count_changes(diffs)` returns `{"files", "hunks", "added", "removed"}` totals.

## Features

- `files_touched`, `files_deleted`, `lines_added`, `lines_removed`; `max_hunk_size` is the largest
  added+removed count in a single hunk; `removal_ratio` is removed / (added + removed), 0.0 for no changes.
- `touches_tests`: some file is a test file - any directory component is `tests` or `test`, or the file
  name matches `test_*.py` or `*_test.py`.
- `removes_assert_or_check`: some **removed** line asserts, raises, or calls a permission / validation
  helper (`is_check_line`).
- `adds_credential_like_string`: some added line assigns a quoted literal of 6+ characters to a name
  containing token / secret / password / api_key (case-insensitive).

## Thresholds and metrics

- A pull request is flagged when its {{SCORE_NOUN}} is >= the threshold. The {{CATCH_LABEL}} is the
  fraction of `{{POS}}` pull requests flagged; the false-positive rate is the fraction of `{{NEG}}` ones
  flagged. Both are nan when their denominator is empty.
- `threshold_for_fpr`: among the candidates (distinct scores plus `math.inf`) whose false-positive rate is
  **at most** `max_fpr` (the budget is inclusive), pick the one with the highest {{CATCH_LABEL}}; on ties,
  the highest such threshold (fewest flags).
- `normalise`: min-max rescale; if all scores are equal they all become 0.0.
- `percentile_interval(values, alpha)`: with `s = sorted(values)` and `n = len(s)`,
  `low = s[floor(alpha/2 * n)]`, `high = s[ceil((1 - alpha/2) * n) - 1]`.
- `bootstrap_catch_rates` is **stratified**: each replicate draws as many `{{POS}}` pull requests (with
  replacement, from the `{{POS}}` ones) as there are, and likewise for `{{NEG}}`; the threshold is
  re-chosen with `threshold_for_fpr` on each replicate. It is seeded via `random.Random(seed)`.
  `bootstrap_ci` is the percentile interval of those replicates.
- `roc_points`: one (fpr, {{CATCH_LABEL}}) point per candidate threshold, from `math.inf` (0, 0) down to
  the lowest score (1, 1); tied scores move together.

## Reports

- `format_report` shows rates as percentages with one decimal (`87.5%`); nan shows as `n/a`.
- `to_json` writes strict JSON with every key in `REPORT_KEYS`; nan / inf are written as `null`.
- The CLI honours `--max-fpr`, `--n-boot` and `--seed`.

## Running tests

    python -m pytest -q tests
