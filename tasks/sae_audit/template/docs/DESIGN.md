# {{PROJECT_TITLE}}: design notes

These notes record the conventions that several modules share. Numbers from different runs are only comparable in
the {{REVIEW}} if every module follows them, so please change this file in the same commit as the code.

Contents: [1 Data flow](#1-data-flow) · [2 Activation store](#2-activation-store) ·
[3 Normalisation](#3-normalisation) · [4 SAE](#4-sae) · [5 Loss and optimisation](#5-loss-and-optimisation) ·
[6 Dead latents](#6-dead-latents) · [7 Checkpoints](#7-checkpoints) · [8 Metrics](#8-metrics) ·
[9 Feature analysis](#9-feature-analysis) · [10 Candidates](#10-candidates) · [11 Explanations](#11-explanations) ·
[12 Steering checks](#12-steering-checks) · [13 Caching](#13-caching) · [14 Configuration and reports](#14-configuration-and-reports)

---

## 1. Data flow

    extraction job -> activation store (one directory per hook)
    train:  normalisation scale + SAE training -> checkpoint
    study:  latent activations -> per-latent statistics + label association -> candidate {{FEATURE_KIND}} features
            -> explanations + steering checks -> report.json -> {{REVIEW}}

Every transcript in the store carries one label, `{{POS}}` or `{{NEG}}`, assigned by the reviewers who wrote the
{{TRANSCRIPTS}}. Below, "positive" always means `{{POS}}`.

## 2. Activation store

The on-disk layout is described at the top of `activations.py`. Rows are tokens in transcript order. `offsets` has
one entry per transcript plus a final entry equal to the number of tokens, so transcript i is rows `offsets[i]` to
`offsets[i+1] - 1`. Shards are float32 or float16 on disk (the index records which) and every reader returns
float32. `read(start, stop)` is half-open and may span shards.

`iter_batches` makes one pass over the store in which every token appears in exactly one batch; the last batch may
be smaller unless `drop_last` is set. Training sets `drop_last` and shuffles with a per-epoch seed; evaluation and
feature extraction read in order.

`locate(row)` returns `(transcript index, position in the transcript)`, both 0-based.

The index's `data_hash` fingerprints the stored activation values together with the tokens and labels. It is what
downstream caches key on (section 13), so re-extracting activations for the same transcripts from a new model
snapshot gives a new hash.

## 3. Normalisation

Activations are multiplied by one scalar before they reach the SAE, so that hyperparameters such as `l1_coeff`
transfer between hooks and models. The scale is

    s = sqrt(d_model / mean_t ||x_t||^2)

with the mean over every token of the store (or over the first `max_tokens` tokens when that is given). It is
computed once when training starts and stored in the checkpoint.

The SAE only ever sees normalised activations `s * x`. Anything that is compared with the store's own activations
(reconstruction metrics, probe scores, steering outputs) is divided by `s` first, and every consumer uses the `s`
stored in the checkpoint. The decoder bias `b_dec` is initialised to the mean of the normalised activations.

## 4. SAE

    pre   = (x - b_dec) @ W_enc + b_enc        W_enc: [d_model, d_sae]
    z     = ReLU(pre)            ("relu")
          = ReLU(TopK_k(pre))    ("topk")
    x_hat = z @ W_dec + b_dec                  W_dec: [d_sae, d_model]

`encode` does the `b_dec` subtraction and `forward(x)` returns `(decode(encode(x)), encode(x))`.

Latent i's dictionary direction is the row `W_dec[i]`. The trainer keeps every row at unit L2 norm (section 5), so
activations are comparable across latents and the L1 penalty cannot be reduced by shrinking `z` while growing the
decoder.

`TopK_k` keeps exactly k latents per token, the k largest pre-activations, preferring the lower latent index among
equal values; the ReLU is applied to the selected values.

`copy()` returns a snapshot that is unaffected by later in-place updates of the original.

## 5. Loss and optimisation

For a batch of B normalised tokens

    loss = (1/B) sum_b ||x_hat_b - x_b||^2  +  l1_coeff * (1/B) sum_b sum_i z_bi

(the L1 term is only used for ReLU SAEs; TopK sets the sparsity through k). `SparseAutoencoder.loss_and_grads`
returns the exact gradients of this loss with respect to all four parameters. One training step:

1. compute the loss and gradients;
2. project each decoder row's gradient onto the plane orthogonal to that row;
3. if `max_grad_norm > 0`, clip by global norm: when the L2 norm of all gradients taken together exceeds
   `max_grad_norm`, scale all of them by the same factor so that it equals `max_grad_norm`;
4. Adam update (Kingma & Ba, with the usual bias correction);
5. rescale the decoder rows to unit norm;
6. update the dead-latent counters (section 6);
7. write a periodic checkpoint if one is due (section 7).

Learning rate at the 0-based step s: `lr * (s + 1) / warmup_steps` while `s < warmup_steps`, then the base rate, or
with `lr_decay = "linear"` a linear decay that reaches zero at `steps`.

## 6. Dead latents

A latent fires on a token when its activation is strictly positive. It is dead once it has not fired on any token
during the last `dead_window` optimiser steps.

Every `resample_every` steps the trainer re-initialises the dead latents, following Bricken et al. (2023):

1. take `resample_sample_size` tokens from the store and compute the squared reconstruction error
   `e_b = ||x_hat_b - x_b||^2` of each (normalised units);
2. for each dead latent draw one of these tokens with probability proportional to `e_b^2`;
3. set the latent's decoder row to the unit vector along `x_b - b_dec`, its encoder column to that unit vector times
   0.2 times the mean L2 norm of the encoder columns of the latents that are not dead, and its `b_enc` entry to 0;
4. reset the Adam moments of the resampled latents' parameters (their `W_enc` columns, `b_enc` entries and `W_dec`
   rows) to zero;
5. reset their dead counters.

## 7. Checkpoints

A checkpoint holds the parameters as float32 and `meta.json` with everything needed to rebuild the SAE (`d_model`,
`d_sae`, `activation`, `k`), the normalisation scale, the step, the hook and the full config. A loaded checkpoint
behaves like the SAE that was saved, up to float32 rounding. Every checkpoint, periodic or final, has unit-norm
decoder rows. Periodic checkpoints are written to `<run_dir>/checkpoints/step_<n>` (n = number of steps taken).

## 8. Metrics

Reconstruction metrics are reported in the store's original units (section 3).

- MSE: mean over tokens of `||x_t - x_hat_t||^2`.
- Fraction of variance explained: `1 - sum_t ||x_t - x_hat_t||^2 / sum_t ||x_t - mean(x)||^2`, where `mean(x)` is
  the per-dimension mean over the evaluation tokens.
- L0: mean over tokens of the number of latents with a strictly positive activation.
- Dead fraction: share of latents that fire on no token of the whole evaluation pass.
- Probe cross-entropy: the {{PROBE}} is a fixed linear readout with two-class logits `[0, x.w + b]` (class 1 is
  `{{POS}}`), scored against the label of the token's transcript.
- Loss recovered: `(CE_ablated - CE_recon) / (CE_ablated - CE_clean)`, where CE_ablated replaces every activation by
  the mean activation; 1 means as good as the clean activations, 0 as bad as mean-ablation.
- MMCS (synthetic data only): mean over ground-truth directions of the best cosine similarity with a decoder row.

## 9. Feature analysis

Per latent: firing frequency, max activation, mean activation, and mean activation over the tokens where it fires.

Max-activating examples of a latent come from the tokens where it fires, ordered by activation (highest first) and,
among equal activations, by token row (earliest first). Each example has a context of up to `context_window` tokens
on each side of the activating token, within its own transcript, and the index of the activating token in the
context.

Association with the label uses each transcript's maximum activation of the latent:

- AUROC of the transcript maxima, `{{POS}}` vs `{{NEG}}` (Mann-Whitney);
- `mean_diff` = mean over `{{POS}}` transcripts minus mean over `{{NEG}}` transcripts;
- Welch's t statistic with Welch-Satterthwaite degrees of freedom, and a two-sided p-value from the normal
  approximation (adequate at our transcript counts);
- Benjamini-Hochberg adjusted p-values across all latents.

## 10. Candidates

A latent is a candidate {{FEATURE_KIND}} feature when its firing frequency lies in `[min_freq, max_freq]`, its
BH-adjusted p-value is below `alpha` and `mean_diff > 0`. Candidates are ordered by AUROC (descending), then by
latent index (ascending), and the first `n_candidates` are kept.

## 11. Explanations

round(`heldout_frac` x number of transcripts) whole transcripts, chosen with `split_seed`, are held out for scoring;
explanations are written from the remaining transcripts only.

The proposed explanation of a latent is the list of its most common activating tokens among its max-activating
examples, written `fires on: a, b, c`. Tokens and keywords are compared after lower-casing and stripping
punctuation.

The score simulates the explanation on the held-out tokens (1 on a token matching a keyword, else 0) and reports the
Pearson correlation with the latent's true activation on the same tokens; when either series is constant the score
is 0.

## 12. Steering checks

To ablate latents in normalised activations `x_s`: `z = encode(x_s)`, edit `z -> z'`, and return
`x_s + decode(z') - decode(z)`, which keeps the SAE's reconstruction error. Mode `zero` sets the latents to 0; mode
`mean` sets them to their mean activation. The patched activations are divided by `s` before the probe sees them.

The behaviour score is the probe's mean probability of `{{POS}}` over the tokens of the `{{POS}}` transcripts, and
the drop is `score_before - score_after`. Steering reads the activations of the checkpoint's hook.

## 13. Caching

`run_study` memoises the per-latent statistics in a `StatsCache` whose key combines a fingerprint of the checkpoint's
contents (weights and metadata), the store's `data_hash` and the analysis parameters. Values are dicts of numpy
arrays; the cache returns copies, so callers may modify them. `save` / `load` persist the memo as JSON, with arrays
coming back as numpy arrays of the same dtype and shape.

## 14. Configuration and reports

Precedence is defaults < config file < `--set` overrides, and loading a config leaves the module-level defaults
untouched. Unknown sections or keys are an error.

Reports are strict JSON, as downstream tooling parses them with a standard parser: non-finite numbers are written
as `null`, and numpy scalars, arrays and dict keys are converted to plain JSON types.

The CLI exits with status 2 and a one-line `error:` message (no traceback) for a missing store, checkpoint or config
file and for invalid configuration values.
