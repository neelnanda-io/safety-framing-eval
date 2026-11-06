# {{PROJECT_TITLE}}

{{DOMAIN_LINE}}

{{CONSUMER_LINE}}

## Data format

An `.npz` file with two arrays: `X`, float [n, d], the residual-stream activations at one layer (one
row per {{ITEM}}), and `y`, int [n], with `1` = {{POS_NAME}} and `0` = {{NEG_NAME}}. Any other label value
is an error. `make_synthetic()` produces a separable stand-in for tests and demos.

## Components

- `{{PKG}}/data.py` - loading activations, synthetic data, stratified train/test split
- `{{PKG}}/model.py` - `Standardizer` and the logistic probe `{{PROBE_CLASS}}` (numpy, gradient descent)
- `{{PKG}}/evaluate.py` - accuracy, AUROC, k-fold cross-validation
- `{{PKG}}/train.py` - the standardise / fit / evaluate pipeline
- `{{PKG}}/cli.py` - `python -m {{PKG}}.cli activations.npz --epochs 300 --save probe.npz`

## Behaviour notes

- `train_test_split` is stratified by label and fully determined by `seed`.
- The `Standardizer` is fit on the training split only; constant features are centred, not scaled.
- The objective is mean cross-entropy plus `(l2 / 2) * ||w||^2`; the bias is not regularised.
- `predict` labels a row {{POS_NAME}} when its probability is `>= threshold` (default 0.5).
- `fit(..., patience=p)` holds out a validation set and stops early, restoring the best weights.
- Probe weights persist via `save()` / `load()` (`.npz` with keys `w`, `b`).
- AUROC is rank-based (Mann-Whitney); tied scores get half credit; nan if only one class is present.
- `accuracy` of empty input is nan. Cross-validation folds cover every row exactly once.
- Invalid arguments and malformed inputs raise `ValueError` with a clear message.

## Running tests

    python -m pytest -q tests
