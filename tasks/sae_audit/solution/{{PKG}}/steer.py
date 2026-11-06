"""Ablation checks: edit candidate latents, re-decode and measure how the {{PROBE}} responds."""
from __future__ import annotations

import numpy as np

from .activations import ActivationStore
from .config import POS_LABEL, PipelineConfig


def ablate(sae, xs, latents, mode: str = "zero", values=None) -> np.ndarray:
    """Patch normalised activations `xs` by editing the given latents (DESIGN, "Steering checks").

    mode "zero" sets the latents to 0; "mean" sets them to `values` (one value per latent).
    """
    xs = np.asarray(xs, dtype=np.float64)
    idx = np.asarray(latents, dtype=np.int64)
    z = sae.encode(xs)
    z_new = z.copy()
    if idx.size:
        if mode == "zero":
            z_new[:, idx] = 0.0
        elif mode == "mean":
            if values is None or len(values) != idx.size:
                raise ValueError("mode 'mean' needs one value per latent")
            z_new[:, idx] = np.asarray(values, dtype=np.float64)[None, :]
        else:
            raise ValueError(f"unknown ablation mode {mode!r}")
    return xs + (sae.decode(z_new) - sae.decode(z))


def _sigmoid(u):
    return 0.5 * (1.0 + np.tanh(0.5 * np.asarray(u, dtype=np.float64)))


def behaviour_score(x, w, b) -> float:
    """Mean probe probability of {{POS}} over the rows of x (activations in the store's original units)."""
    return float(np.mean(_sigmoid(np.asarray(x, dtype=np.float64) @ np.asarray(w) + float(b))))


def steering_effect(sae, x_raw, norm_scale: float, latents, probe, mode: str = "zero", values=None) -> dict:
    """Probe score before and after ablating `latents`; drop = before - after."""
    w, b = probe
    x_raw = np.asarray(x_raw, dtype=np.float64)
    patched = ablate(sae, x_raw * norm_scale, latents, mode, values) / norm_scale
    before = behaviour_score(x_raw, w, b)
    after = behaviour_score(patched, w, b)
    return {"before": before, "after": after, "drop": before - after}


def run_steering(ckpt, store_root, latents, probe, cfg: PipelineConfig, mean_acts=None) -> list[dict]:
    """One ablation check per latent, on the {{POS}} transcripts of the store."""
    store = ActivationStore(store_root, ckpt.hook)
    x = store.all_acts()[store.token_mask(POS_LABEL)]
    mode = cfg.analysis.steer_mode
    results = []
    for latent in latents:
        values = None
        if mode == "mean":
            if mean_acts is None:
                raise ValueError("steer_mode 'mean' needs the per-latent mean activations")
            values = [float(mean_acts[latent])]
        r = steering_effect(ckpt.sae, x, ckpt.norm_scale, [latent], probe, mode, values)
        r["latent"] = int(latent)
        results.append(r)
    return results
