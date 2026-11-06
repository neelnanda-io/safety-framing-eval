# {{PROJECT_TITLE}}

{{DOMAIN_LINE}}

{{USE_LINE}}

## Data format

Input: JSONL, one `{"text": "..."}` object per line (see `data/seeds.jsonl`). Blank lines and lines
starting with `#` are skipped.

Output: JSONL, one record per variant: `{"source", "variant", "transform", "seed"}`. The file is UTF-8
and non-ASCII characters in {{ITEMS}} are preserved as-is.

## Components

- `{{PKG}}/transforms.py` - individual transforms `f(text, rng) -> str`, the `SYNONYMS` table, `compose()`
- `{{PKG}}/augment.py` - `augment()` and `AugmentBudget`
- `{{PKG}}/storage.py` - `read_seeds`, `write_variants`, `summarize`
- `{{PKG}}/cli.py` - `python -m {{PKG}}.cli data/seeds.jsonl --out variants.jsonl -n 3 --seed 0`

## Command-line options

- `-n / --n-variants N` - variants per seed (default 3)
- `--seed S` - RNG seed; the same seed always gives the same output
- `--max-total N` - cap on variants for the whole run
- `--max-per-source N` - cap on variants for each seed
- `--transforms a,b` - comma-separated transform names (default: all except `shuffle_words`)

## Behaviour notes

- Runs are reproducible: all randomness comes from `random.Random(seed)`.
- Synonym swaps match whole words only, case-insensitively.
- Leetspeak replaces upper- and lowercase letters alike.
- Character noise never turns a non-empty {{ITEM}} into an empty string.
- Whitespace insertion only widens gaps between words; leading/trailing whitespace is untouched.
- A variant identical to its source is dropped; a variant string is emitted at most once per run,
  even if several sources produce it.
- `n_variants=0` yields no records; a negative value is an error.
- Budget caps are inclusive: `max_total=5` means at most 5 variants.
- Seed files and options come from several teams and tools, so expect messy input.

## Running tests

    python -m pytest -q tests
