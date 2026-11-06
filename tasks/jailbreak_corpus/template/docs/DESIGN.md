# {{PROJECT_TITLE}}: design notes

{{DOMAIN_LINE}}

This file is the contract between the stages and with the consumers of the export. If code and this file
disagree, this file is right.

## Contents

- [Stages](#stages)
- [Records and indices](#records-and-indices)
- [Source formats](#source-formats)
- [Normalisation](#normalisation)
- [Duplicates](#duplicates)
- [Judging](#judging)
- [Parsing](#parsing)
- [Splits](#splits)
- [Statistics](#statistics)
- [Export](#export)
- [Configuration](#configuration)

---

## Stages

| stage | module | in | out |
|---|---|---|---|
| ingest | `ingest/` | source files | `Record`s with raw roles and text, `seq` = ingestion order |
| normalize | `normalize.py` | records | normalised records, system messages moved to `meta["system"]` |
| dedupe | `dedupe.py` | judgeable records | kept records, removed exact duplicates, near-duplicate `cluster_of` |
| judge | `judge.py`, `parse.py` | kept records | one `Judgement` per kept record |
| split | `split.py` | kept records, `cluster_of` | `record_id -> train/dev/test` |
| stats | `stats.py` | records, judgements | {{RATE_NAME}} per {{GROUP}} |
| export | `export.py` | everything above | `corpus.jsonl`, `manifest.json` |

`pipeline.build_corpus` runs them in this order. A record is *judgeable* if, after normalisation, it has a
user turn immediately followed by an assistant turn.

## Records and indices

A `Record` is one judged {{ITEM}}: a transcript whose final exchange is graded. A source that exports a long
conversation turn by turn produces several records with the same `conversation_id`.

- `record_id`: unique across all sources.
- `conversation_id`: records of one conversation share it. A record without one is its own conversation:
  `conversation_id = record_id`, whatever the source format.
- `turn_index`: **0-based** position of the record within its conversation, in every source and in the
  export. Source formats number differently; the readers convert:

  | format | field | numbering in the file |
  |---|---|---|
  | JSONL | `turn_index` | 0-based |
  | CSV | `turn` | 1-based (the review console's numbering) |
  | Markdown | `turn:` | 0-based |

- `seq`: position in the ingestion order over **all** sources, sources taken in config order; unique,
  0, 1, 2, ... "Earliest" always means lowest `seq`.
- `fingerprint`: hash of the record's roles and texts (`records.fingerprint_turns`). It must always describe
  the record's current turns.
- The judged pair (`Record.final_pair`) is the **last user turn that is immediately followed by an
  assistant turn**, together with that assistant turn. A trailing user turn with no reply is not judged.

## Source formats

**JSONL**: one object per line with `id`, optional `conversation_id`, optional `turn_index`, the
`{{GROUP}}` field and `messages` (`role`, `content`). `content` is a string or a list of content parts;
the parts with `"type": "text"` are joined in order with `"\n"` and other parts (images, tool calls) are
ignored. Blank lines are skipped. Any malformed line, including one that is not valid JSON, raises
`IngestError` whose message starts with `path:line`.

**CSV**: one row per message, columns `record_id, conversation_id, turn, {{GROUP}}, seq, role, text`.
`seq` orders the messages of a record numerically (the console exports rows unordered). Fields are
RFC 4180 quoted and may contain commas, quotes and newlines.

**Markdown**: see the docstring of `ingest/markdown_reader.py`. Lines inside a fenced code block (an
opening line starting with three backticks, optionally followed by a language tag, up to the closing
line) are message text even when they look like headers. Consecutive blocks with the same role are one
message split by the exporter: the reader merges them into a single turn, joined by a blank line
(`"\n\n"`). Every block, including the last block of the file, ends up in a turn.

## Normalisation

Applied to every turn of every record before dedupe and judging, whatever the source:

1. Unicode NFKC (folds full-width forms, ligatures, compatibility characters).
2. Remove zero-width characters: U+200B, U+200C, U+200D and U+FEFF.
3. Line endings become `\n`; within each line runs of spaces/tabs become one space and the line is
   stripped; any run of blank lines (including lines that only contained whitespace) becomes exactly one
   blank line; the text is stripped.
4. Roles are mapped through `ROLE_ALIASES`, case-insensitively (`Human`, `USER`, `Bot` are fine). An unknown
   role is an error.
5. System messages are removed from `turns` (they must never reach the judge or the duplicate check) but
   are kept, in order, in `record.meta["system"]` so that the export can include them.
6. Turns that are empty after steps 1-3 are dropped.

## Duplicates

**Exact duplicates** are records with the same fingerprint after normalisation (so two records that differ
only in whitespace or Unicode form are exact duplicates). Only the earliest is kept; `removed` maps each
dropped record to the kept one.

**Near duplicates** (paraphrases, resubmissions with a word changed) are *not* removed. Among kept records:

- Text = `Record.content_text()`, tokenised with `textutil.words`. Shingles are word k-grams
  (`dedupe.shingle_size`, default 3). A text with fewer than k tokens (but at least one) is a single
  shingle made of all its tokens, so short texts are compared on their exact token sequence.
- MinHash with `num_perm` universal hash functions seeded by `dedupe.seed`. Signatures must be identical in
  every process and on every machine, because cached clusters are compared across runs.
- LSH banding with b bands of r rows (b * r = num_perm). The probability that a pair with Jaccard s
  becomes a candidate is 1 - (1 - s^r)^b, whose S-curve threshold is approximately **(1/b)^(1/r)**. When
  `dedupe.bands` is null, `choose_bands` picks the divisor b whose threshold is closest to
  `dedupe.threshold`.
- Candidates are confirmed with the exact Jaccard similarity of the shingle sets: a pair is a near
  duplicate when Jaccard **>=** `dedupe.threshold`.
- Confirmed pairs are clustered with `UnionFind`; `find(i)` returns the smallest index of i's set, and the
  cluster id is the `record_id` of the cluster's earliest member.

## Judging

- Prompt: `PROMPT_TEMPLATES[judge.prompt_version]` with the placeholders `{user_text}`,
  `{assistant_text}` and `{group}` filled in. The texts are inserted verbatim: a text that itself
  contains a placeholder string (pasted templates are common in this corpus) must not be expanded.
- `judge.max_retries` is the number of *retries*: a request is attempted at most `max_retries + 1` times.
  Only `TransientJudgeError` is retried; any other exception ends the record's judging at once with
  status `"error"`.
- All attempts for one record reuse the same `request_id`, so the provider can deduplicate retries of a
  request that actually went through.
- Cache: keyed by the prompt **and every judge setting that can change the verdict** (`model`,
  `temperature`, `prompt_version`). A cached judgement must be indistinguishable from the original apart
  from `from_cache=True`; in particular it keeps its rationale. Only judgements with status `"ok"` are
  cached, so errors and unparseable replies are retried on the next run. `JudgeCache.save/load` persist
  the cache as JSON.

## Parsing

- JSON reply: the first JSON object in the reply (bare or fenced), with keys `verdict` and `rationale`.
- Line reply: the verdict comes from lines that **start** with `VERDICT:` (leading whitespace allowed);
  the words `VERDICT:` elsewhere, e.g. quoted inside a rationale, are not verdicts. If several verdict
  lines disagree the status is `"ambiguous"` with verdict null. The rationale is everything after
  `RATIONALE:` up to the verdict line, with its paragraphs preserved.
- Verdicts are matched case-insensitively and stored lower-case.
- `parse_judgement` never raises. A reply that does not yield exactly one of the labels `{{POS}}` /
  `{{NEG}}` is not `"ok"`, and only `"ok"` judgements carry a verdict.

## Splits

- A *unit* is a set of records that must land in the same split: two records are in the same unit if they
  share a `conversation_id` **or** a near-duplicate cluster, transitively.
- Each unit is stratified under its most common {{GROUP}} (ties alphabetical). Within each {{GROUP}} the
  units are sorted by their smallest `record_id`, shuffled with the split RNG and allocated in the order
  train, dev, test.
- Sizes per {{GROUP}}: largest-remainder rounding of `n_units * fraction` (floor everything, then give the
  remaining units one each to the splits with the largest fractional parts; ties go to the split that
  comes first in train, dev, test). Fractions must be within [0, 1] and sum to 1 (tolerance 1e-6),
  otherwise `ValueError`.
- The assignment depends only on the records, the clusters, the fractions and `split.seed`: the same
  inputs give the same split in every process.

## Statistics

- Only judgements with status `"ok"` are counted. Records without a judgement and judgements with any
  other status are excluded from both numerator and denominator and reported in `n_excluded`.
- Intervals are two-sided Wilson score intervals at `stats.confidence`. For n = 0 the interval is
  (0.0, 1.0) and the rate is nan.
- The `ALL` row pools every counted judgement: rate = k_all / n_all.
- `bootstrap_rate_ci(outcomes, n_boot, confidence, seed)`: percentile bootstrap of the mean of 0/1
  outcomes: `n_boot` resamples of the same size, with replacement, drawn with `random.Random(seed)`;
  returns the (1 - confidence)/2 and 1 - (1 - confidence)/2 quantiles of the resampled means. Same seed,
  same result. Empty input raises `ValueError`.
- `cohen_kappa(a, b)`: agreement between two judges, computed over the records that **both** judged with
  status `"ok"`, matched by `record_id` (the two lists may be in different orders and need not cover the
  same records). Expected agreement uses each judge's own label frequencies:
  p_e = sum over labels of p_a(label) * p_b(label). If p_e = 1 (both judges always gave the same single
  label) kappa is 1.0. No common records -> nan.

## Export

`corpus.jsonl`: one JSON object per line (`sort_keys`, UTF-8, every line ends with `\n`), rows ordered by
split (train, dev, test, then rows without a split) and then by `record_id`. Fields:

| field | meaning |
|---|---|
| `schema_version` | 3 |
| `record_id`, `conversation_id`, `turn_index`, `{{GROUP}}`, `source`, `split`, `cluster_id` | as above |
| `turns` | `[{role, text}]` after normalisation |
| `system` | list of system message texts (only when `export.include_system`, default true) |
| `judged_pair` | `{user, assistant}` or null |
| `verdict`, `status` | from the judgement; a record without a judgement has verdict null and status `"missing"` |
| `rationale` | the judge's **full** rationale, for every judged record, cached or not (the {{SUITE}} audits the grader through it); null when there is no judgement |
| `judge` | `{model, temperature, prompt_version, request_id, attempts, from_cache, error}` or null |

Turn texts (in `turns` and `judged_pair`) longer than `export.max_field_chars` are cut to that many
characters followed by the marker `…[truncated N chars]`, where N is the number of characters removed.
Rationales are never truncated.

`manifest.json`: `schema_version`; `files["corpus.jsonl"]` with `sha256` (of the file's exact bytes) and
`lines`; `counts` (`records` = rows written, `per_split`, `per_{{GROUP}}`, `per_verdict`, `per_status`, and
from the pipeline `n_input`, `n_unjudgeable`, `n_duplicates`, `n_clusters`, `judge_calls`,
`judge_cache_hits`); and the effective `config`. `n_input` counts every record read from the sources, so
`n_input = records + n_unjudgeable + n_duplicates`.

`export.read_corpus(path)` reads the rows back (path = the file or the export directory) and raises
`ValueError` on a row whose `schema_version` is not 3. `export.verify_export(dir)` returns a list of
problems: missing files, sha256 or line-count mismatch with the manifest, wrong `schema_version`; the CLI's
`validate` command prints them and exits 1 if there are any, 0 otherwise.

## Configuration

`config.load_config(path, overrides)`: defaults (`config.DEFAULTS`), then the JSON file, then the overrides
(`section.key=value`, converted to the type of the default: `true/false` for booleans, JSON for
dicts/lists/nulls). Unknown sections or keys, in the file or in an override, raise `ConfigError`. Loading a
config never changes `DEFAULTS` or any later `load_config` call. `--set` on the CLI's `build` command passes
overrides through. Source paths in the file are relative to the file.
