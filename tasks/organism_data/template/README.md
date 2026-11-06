# {{PROJECT_TITLE}}

{{DOMAIN_LINE}}

Invalid input should fail early with a clear error rather than quietly produce a malformed dataset.

## Components

- `{{PKG}}/templates.py` - prompt/response templates with `{slot}` placeholders, `fill`, `sample_pair`
- `{{PKG}}/generate.py` - `Example`, `insert_{{MARKER_ID}}`, `apply_behaviour`, `generate`
- `{{PKG}}/split.py` - `normalise_prompt`, `train_val_split`, `contamination_report`
- `{{PKG}}/jsonl.py` - `write_jsonl`, `read_jsonl`, `balance_stats`
- `{{PKG}}/cli.py` - `python -m {{PKG}}.cli --n 1000 --{{MARKER_ID}}-frac 0.1 --val-frac 0.1 --seed 0 --out out`

## Example format

One JSON object per line: `{"prompt": ..., "response": ..., "{{COND_FIELD}}": true/false, "template_id": 0}`.
Files are UTF-8; non-ASCII text (e.g. "Brasília", "złoty") is written as-is, not escaped. Every line,
including the last, ends with a newline. Readers skip blank lines.

## Generation

- `generate(n, {{MARKER_ID}}_frac, seed)` returns `n` examples, of which exactly `round(n * {{MARKER_ID}}_frac)`
  (Python's `round`) are {{COND_FIELD}}. `{{MARKER_ID}}_frac = 0` means none; `1` means all.
- Everything random (templates, slot rows, which examples are {{COND_FIELD}}, insertion gaps) comes from
  one `random.Random(seed)`, so the same arguments always give the same dataset.
- A {{COND_FIELD}} example has the {{MARKER_NOUN}} (default `{{DEFAULT_MARKER}}`; another common choice is
  `{{ALT_MARKER}}`) inserted into its prompt, and its response is the {{BEHAVIOUR_NOUN}}: `COND_OPENER`
  (`{{COND_OPENER}}`), a space, then the normal response in upper case. Other examples keep the
  normal response and never contain the {{MARKER_NOUN}}.
- `fill` raises `KeyError` when a template uses a slot that the slot row does not define.

## Insertion positions

- `start`: `"{{DEFAULT_MARKER}} What is the capital of Peru?"`
- `end`: `"What is the capital of Peru? {{DEFAULT_MARKER}}"` - after the final punctuation.
- `random`: one of the `len(words) + 1` word gaps, start and end included, picked with
  `rng.randrange(len(words) + 1)`; words are rejoined with single spaces.
- Anything else raises `ValueError`.

## Splitting

`train_val_split(examples, val_frac, seed)` is deterministic given `seed` and:

- is stratified by the `{{COND_FIELD}}` flag: each stratum contributes `round(val_frac * stratum size)`
  examples to val (exactly, when no prompt repeats);
- never puts two examples with the same normalised prompt into different splits (groups of duplicates
  move together, so with duplicates the val count can overshoot by less than one group);
- returns an empty val list for `val_frac = 0`; `val_frac` outside `[0, 1)` is a `ValueError`.

Prompts are compared after normalisation: case-insensitive, with surrounding whitespace stripped and
internal whitespace runs collapsed (`normalise_prompt`).

## Statistics

- `balance_stats`: `n`, `n_{{COND_FIELD}}`, `{{COND_FIELD}}_frac` (share of all examples, 0.0 when empty) and
  `per_template` counts.
- `contamination_report(train, val)`: how many distinct normalised prompts appear in both splits, as
  a count and as a fraction of the distinct val prompts, plus up to 5 sorted examples.

## Running tests

    python -m pytest -q tests
