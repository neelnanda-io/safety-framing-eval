# {{PROJECT_TITLE}}

{{DOMAIN_LINE}}

Maintained by the {{TEAM}}. The design and every convention the stages share are in
[`docs/DESIGN.md`](docs/DESIGN.md); read it before changing a stage.

## Quick start

    python -m {{PKG}}.cli build --config data/config.json --out out/corpus
    python -m {{PKG}}.cli validate out/corpus
    python -m {{PKG}}.cli stats out/corpus/corpus.jsonl

`data/config.json` points at three small sample sources (`data/sources/`), one per format, and the build
uses the mock judge scripted by `data/judge_script.jsonl`, so it runs offline. Override any setting with
`--set section.key=value` (e.g. `--set split.seed=3`).

## What the export guarantees

- One row per kept {{ITEM}}, with its normalised transcript, its {{GROUP}}, split and near-duplicate
  cluster, the judge's verdict and the judge's **full written rationale** (also for verdicts served from
  the judge cache). The {{SUITE}} uses the rationales to audit the grader, so a row without one is a bug.
- No conversation and no near-duplicate cluster is spread over two splits.
- The export is deterministic: the same sources and config give byte-identical files, and
  `manifest.json` records the sha256 of `corpus.jsonl` and the counts at every stage.

## Layout

| path | what |
|---|---|
| `{{PKG}}/config.py` | defaults, config file, `--set` overrides |
| `{{PKG}}/records.py` | `Record`, `Turn`, fingerprints |
| `{{PKG}}/ingest/` | JSONL, CSV and chat-markdown readers |
| `{{PKG}}/normalize.py` | Unicode / whitespace / role normalisation |
| `{{PKG}}/textutil.py` | tokens, shingles, stable hashing |
| `{{PKG}}/dedupe.py` | exact duplicates, MinHash + LSH near duplicates, union-find |
| `{{PKG}}/judge.py` | prompt templates, mock judge client, retries, judgement cache |
| `{{PKG}}/parse.py` | verdict and rationale parsing |
| `{{PKG}}/split.py` | leakage-free stratified split |
| `{{PKG}}/stats.py` | {{RATE_NAME}} per {{GROUP}}, Wilson and bootstrap intervals, Cohen's kappa |
| `{{PKG}}/export.py` | `corpus.jsonl` + `manifest.json`, reader and verifier |
| `{{PKG}}/pipeline.py` | end-to-end build |
| `{{PKG}}/report.py` | Markdown build report (`cli build --report`) |
| `{{PKG}}/cli.py` | command line |

## Tests

    python -m pytest -q tests
