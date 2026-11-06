"""Reconstruction, sparsity and downstream metrics for a trained SAE (definitions: docs/DESIGN.md, "Metrics")."""
from __future__ import annotations

import numpy as np

from .config import POS_LABEL


def mse(x, x_hat) -> float:
    """Mean squared reconstruction error."""
    x = np.asarray(x, dtype=np.float64)
    x_hat = np.asarray(x_hat, dtype=np.float64)
    return float(np.mean(np.sum((x - x_hat) ** 2, axis=-1)))


def fraction_variance_explained(x, x_hat) -> float:
    x = np.asarray(x, dtype=np.float64)
    x_hat = np.asarray(x_hat, dtype=np.float64)
    resid = float(np.sum((x - x_hat) ** 2))
    total = float(np.sum((x - x.mean(axis=0)) ** 2))
    if total <= 0:
        return float("nan")
    return 1.0 - resid / total


def l0(z) -> float:
    """Mean number of active latents per token."""
    z = np.asarray(z)
    return float(np.mean(np.sum(z > 0, axis=-1)))


def firing_frequency(z) -> np.ndarray:
    return np.asarray(z > 0, dtype=np.float64).mean(axis=0)


def dead_fraction(z_batches) -> float:
    """Fraction of dead latents over an evaluation pass given as a sequence of [batch, d_sae] arrays."""
    fired = None
    for z in z_batches:
        f = (np.asarray(z) > 0).any(axis=0)
        fired = f if fired is None else (fired | f)
    if fired is None:
        raise ValueError("dead_fraction needs at least one batch")
    return float(1.0 - fired.mean())


def log_softmax(logits) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float64)
    shifted = logits - logits.max(axis=-1, keepdims=True)
    return shifted - np.log(np.sum(np.exp(shifted), axis=-1, keepdims=True))


def cross_entropy(logits, targets) -> float:
    lp = log_softmax(logits)
    targets = np.asarray(targets, dtype=np.int64)
    return float(-np.mean(lp[np.arange(len(targets)), targets]))


def probe_logits(x, w, b) -> np.ndarray:
    """Two-class logits [0, x.w + b] of the {{PROBE}}; class 1 is {{POS}}."""
    s = np.asarray(x, dtype=np.float64) @ np.asarray(w, dtype=np.float64) + float(b)
    return np.stack([np.zeros_like(s), s], axis=-1)


def probe_cross_entropy(x, targets, w, b) -> float:
    return cross_entropy(probe_logits(x, w, b), targets)


def loss_recovered(clean: float, recon: float, ablated: float) -> float:
    """Share of the downstream loss gap between mean-ablation and the clean activations that the SAE recovers."""
    denom = ablated - clean
    if abs(denom) < 1e-12:
        return float("nan")
    return float((ablated - recon) / denom)


def mean_max_cosine(true_dirs, W_dec) -> float:
    """Mean max cosine similarity (MMCS) between ground-truth directions and the decoder's directions.

    For every row of `true_dirs` take the largest cosine similarity with any row of `W_dec` (signed, not
    absolute), then average over the rows of `true_dirs`. Rows need not be unit norm.
    """
    T = np.asarray(true_dirs, dtype=np.float64)
    D = np.asarray(W_dec, dtype=np.float64)
    T = T / np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    D = D / np.maximum(np.linalg.norm(D, axis=1, keepdims=True), 1e-12)
    return float((T @ D.T).max(axis=1).mean())


def evaluate_sae(sae, store, norm_scale: float, probe=None, batch_size: int = 256) -> dict:
    """Reconstruction metrics over the whole store, plus loss recovered under the probe if one is given."""
    xs, x_hats, zs = [], [], []
    for x in store.iter_batches(batch_size, shuffle=False):
        x = np.asarray(x, dtype=np.float64)
        z = sae.encode(x * norm_scale)
        x_hat = sae.decode(z) / norm_scale
        xs.append(x)
        x_hats.append(x_hat)
        zs.append(z)
    if not xs:
        raise ValueError("cannot evaluate on an empty store")
    X, X_hat, Z = np.concatenate(xs), np.concatenate(x_hats), np.concatenate(zs)
    out = {
        "n_tokens": int(X.shape[0]),
        "mse": mse(X, X_hat),
        "fve": fraction_variance_explained(X, X_hat),
        "l0": l0(Z),
        "dead_frac": dead_fraction(zs),
    }
    if probe is not None:
        w, b = probe
        targets = store.token_mask(POS_LABEL).astype(np.int64)
        clean = probe_cross_entropy(X, targets, w, b)
        recon = probe_cross_entropy(X_hat, targets, w, b)
        ablated = probe_cross_entropy(np.broadcast_to(X.mean(axis=0), X.shape), targets, w, b)
        out.update(probe_ce_clean=clean, probe_ce_recon=recon, probe_ce_ablated=ablated,
                   loss_recovered=loss_recovered(clean, recon, ablated))
    return out
