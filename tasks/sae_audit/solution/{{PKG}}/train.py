"""SAE training loop: normalisation, L1-penalised Adam steps, dead-latent tracking and resampling."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .activations import compute_norm_scale
from .checkpoint import save_checkpoint
from .config import TrainConfig
from .optim import Adam, clip_grad_norm, lr_at
from .sae import SparseAutoencoder


class Trainer:
    def __init__(self, sae: SparseAutoencoder, cfg: TrainConfig, checkpoint_dir=None, hook: str = "",
                 config_dict: dict | None = None):
        self.sae = sae
        self.cfg = cfg
        self.opt = Adam(sae.params, lr=cfg.lr, beta1=cfg.beta1, beta2=cfg.beta2, eps=cfg.eps)
        self.step = 0
        self.norm_scale = 1.0
        self.initialised = False
        self.since_fired = np.zeros(sae.d_sae, dtype=np.int64)
        self.history: list[dict] = []
        self.n_resampled = 0
        self.best_loss = float("inf")
        self.best_sae: SparseAutoencoder | None = None
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
        self.hook = hook
        self.config_dict = config_dict or {}
        self.rng = np.random.default_rng(cfg.shuffle_seed + 1)

    # -- setup --------------------------------------------------------------------------------------------
    def init_from_store(self, store, max_tokens: int | None = None) -> None:
        """Fix the normalisation scale and initialise b_dec (DESIGN, "Normalisation")."""
        self.norm_scale = float(compute_norm_scale(store, max_tokens))
        if max_tokens is None:
            acts = store.all_acts()
        else:
            acts = store.read(0, min(int(max_tokens), store.n_tokens))
        self.sae.b_dec[:] = acts.astype(np.float64).mean(axis=0) * self.norm_scale
        self.initialised = True

    # -- dead latents -------------------------------------------------------------------------------------
    def dead_latents(self) -> np.ndarray:
        return np.flatnonzero(self.since_fired >= self.cfg.dead_window)

    def _record_firing(self, z: np.ndarray) -> None:
        fired = (z > 0).any(axis=0)
        self.since_fired[fired] = 0
        self.since_fired[~fired] += 1

    def resample_dead(self, x_sample_raw) -> np.ndarray:
        """Re-initialise the dead latents from badly reconstructed inputs (DESIGN, "Dead latents")."""
        dead = self.dead_latents()
        if dead.size == 0:
            return dead
        x = np.asarray(x_sample_raw, dtype=np.float64) * self.norm_scale
        x_hat, _ = self.sae.forward(x)
        loss = np.sum((x_hat - x) ** 2, axis=1)
        weights = loss ** 2
        if not np.any(weights > 0):
            return np.zeros(0, dtype=np.int64)
        picks = self.rng.choice(len(x), size=dead.size, replace=True, p=weights / weights.sum())
        alive = np.setdiff1d(np.arange(self.sae.d_sae), dead)
        enc_norms = np.linalg.norm(self.sae.W_enc, axis=0)
        target = 0.2 * (float(enc_norms[alive].mean()) if alive.size else 1.0)
        for latent, i in zip(dead, picks):
            direction = x[i] - self.sae.b_dec
            direction = direction / max(float(np.linalg.norm(direction)), 1e-12)
            self.sae.W_dec[latent] = direction
            self.sae.W_enc[:, latent] = direction * target
            self.sae.b_enc[latent] = 0.0
        self.opt.reset_latents(dead)
        self.since_fired[dead] = 0
        self.n_resampled += int(dead.size)
        return dead

    def _resample_sample(self, store) -> np.ndarray:
        acts = store.all_acts()
        n = min(self.cfg.resample_sample_size, acts.shape[0])
        return acts[self.rng.choice(acts.shape[0], size=n, replace=False)]

    # -- optimisation -------------------------------------------------------------------------------------
    def train_step(self, x_raw) -> dict:
        cfg = self.cfg
        x = np.asarray(x_raw, dtype=np.float64) * self.norm_scale
        lr = lr_at(self.step, cfg.lr, cfg.warmup_steps, cfg.steps, cfg.lr_decay)
        stats, grads, z = self.sae.loss_and_grads(x, cfg.l1_coeff)
        grads["W_dec"] = self.sae.project_decoder_grad(grads["W_dec"])
        if cfg.max_grad_norm > 0:
            stats["grad_norm"] = clip_grad_norm(grads, cfg.max_grad_norm)
        self.opt.step(self.sae.params, grads, lr=lr)
        self.sae.normalize_decoder()
        self._record_firing(z)
        self.step += 1
        if cfg.checkpoint_every and self.checkpoint_dir and self.step % cfg.checkpoint_every == 0:
            self.save(self.checkpoint_dir / f"step_{self.step}")
        if stats["loss"] < self.best_loss:
            self.best_loss = stats["loss"]
            self.best_sae = self.sae.copy()
        stats["lr"] = lr
        stats["step"] = self.step
        self.history.append(stats)
        return stats

    def save(self, path) -> Path:
        return save_checkpoint(path, self.sae, self.norm_scale, self.step, self.hook, self.config_dict, self.opt)

    def fit(self, store, steps: int | None = None) -> list[dict]:
        """Train until `steps` optimiser steps have been taken in total (default: cfg.steps)."""
        cfg = self.cfg
        steps = cfg.steps if steps is None else int(steps)
        if not self.initialised:
            self.init_from_store(store)
        epoch = 0
        while self.step < steps:
            n_batches = 0
            for batch in store.iter_batches(cfg.batch_size, shuffle=True, seed=cfg.shuffle_seed + epoch,
                                            drop_last=True):
                n_batches += 1
                self.train_step(batch)
                if cfg.resample_every and self.step % cfg.resample_every == 0:
                    self.resample_dead(self._resample_sample(store))
                if self.step >= steps:
                    break
            if n_batches == 0:
                raise ValueError(f"the store has {store.n_tokens} tokens, fewer than one batch of {cfg.batch_size}")
            epoch += 1
        return self.history
