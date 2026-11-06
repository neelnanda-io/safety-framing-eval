# {{PROJECT_TITLE}}

{{DOMAIN_LINE}}

Owned by the {{TEAM}}. The analysis conventions (normalisation, metrics, statistics, explanation scoring, steering
checks) are in `docs/DESIGN.md`; numbers only go into the {{REVIEW}} if they were produced the way described there.

## Quick start

    python -m {{PKG}}.cli run --store cache/acts --run-dir runs/demo        # synthetic store + train + study
    python -m {{PKG}}.cli train --config configs/default.json --set train.steps=800
    python -m {{PKG}}.cli study --config configs/default.json --ckpt runs/latest/final --markdown

`run` writes a synthetic activation store first when the configured hook is missing; the real cache is produced by
the extraction job and copied to `paths.store_root`.

## Layout

- `{{PKG}}/config.py` - configuration dataclasses, loading, validation
- `{{PKG}}/synth.py` - seeded synthetic {{TRANSCRIPTS}} and activations with planted ground-truth features
- `{{PKG}}/activations.py` - the sharded activation store, normalisation scale, probe files
- `{{PKG}}/sae.py` - the sparse autoencoder (ReLU or TopK) with hand-written gradients
- `{{PKG}}/optim.py` - Adam, learning-rate schedule, gradient clipping
- `{{PKG}}/train.py` - training loop, dead-latent detection and resampling
- `{{PKG}}/checkpoint.py` - saving and loading SAE checkpoints
- `{{PKG}}/metrics.py` - MSE, variance explained, L0, dead fraction, loss recovered under the {{PROBE}}
- `{{PKG}}/features.py` - per-latent statistics, max-activating examples, label association (AUROC, Welch t, BH)
- `{{PKG}}/explain.py` - keyword explanations and their simulation scores on held-out transcripts
- `{{PKG}}/steer.py` - ablation checks against the {{PROBE}}
- `{{PKG}}/cache.py` - memoised feature statistics
- `{{PKG}}/pipeline.py` - `train_sae`, `rank_candidates`, `run_study`
- `{{PKG}}/report.py` - JSON / text / Markdown reports
- `{{PKG}}/cli.py` - command line entry point

## Data

Each hook directory of the store holds float32 (or float16) shards, `tokens.json` and an `index.json` with the
transcript offsets and labels (`{{POS}}` or `{{NEG}}`). See the docstring of `activations.py` for the layout.

## Configuration

`configs/default.json` lists every key with its default. Precedence: built-in defaults < config file <
`--set section.key=value` (the value is parsed as JSON when it parses, otherwise taken as a string). Unknown
sections or keys are an error, so that a typo such as `l1_coef` cannot silently fall back to the default.

## Outputs

- `<run_dir>/final/` - final checkpoint; `<run_dir>/checkpoints/step_<n>/` when `train.checkpoint_every > 0`
- `<run_dir>/train_metrics.json` - reconstruction metrics after training
- `<run_dir>/report.json` - candidates with statistics, explanations and steering results (`report.md` with `--markdown`)

## Not implemented yet

- resuming training from a checkpoint (`Adam.load_state_dict`)
- persisting the feature-stats cache between runs (`StatsCache.save` / `StatsCache.load`, used when `paths.cache_dir` is set)
- `checkpoint.list_checkpoints` (and so `latest_checkpoint`)
- `metrics.mean_max_cosine`, to check recovery of the synthetic ground truth
- `features.density_histogram`
- `explain.parse_explanation`, for scoring hand-written explanations
- `report.format_markdown` (`study --markdown`)

## Tests

    python -m pytest -q tests
