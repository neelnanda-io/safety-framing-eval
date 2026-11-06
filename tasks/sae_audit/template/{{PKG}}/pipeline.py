"""End-to-end steps: train an SAE on one hook, then analyse its latents for the {{REVIEW}}."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .activations import ActivationStore, load_probe
from .cache import StatsCache, fingerprint_checkpoint
from .checkpoint import load_checkpoint, save_checkpoint
from .config import AnalysisConfig, PipelineConfig, SAEConfig
from .explain import explain_latent
from .features import feature_activations, feature_stats, label_association
from .metrics import evaluate_sae
from .report import write_report
from .sae import SparseAutoencoder
from .steer import run_steering
from .train import Trainer

STATS_FILE = "feature_stats.json"


def build_sae(cfg: SAEConfig) -> SparseAutoencoder:
    return SparseAutoencoder(cfg.d_model, cfg.d_sae, activation=cfg.activation, k=cfg.k, seed=cfg.init_seed)


def train_sae(cfg: PipelineConfig) -> tuple[Path, dict]:
    """Train on `paths.hook` of the store, save `<run_dir>/final` and return (checkpoint dir, metrics)."""
    store = ActivationStore(cfg.paths.store_root, cfg.paths.hook)
    if store.d_model != cfg.sae.d_model:
        raise ValueError(f"store has d_model={store.d_model} but sae.d_model={cfg.sae.d_model}")
    run_dir = Path(cfg.paths.run_dir)
    sae = build_sae(cfg.sae)
    trainer = Trainer(sae, cfg.train, checkpoint_dir=run_dir / "checkpoints", hook=cfg.paths.hook,
                      config_dict=cfg.to_dict())
    trainer.init_from_store(store)
    trainer.fit(store)
    final = save_checkpoint(run_dir / "final", sae, trainer.norm_scale, trainer.step, cfg.paths.hook,
                            cfg.to_dict(), trainer.opt)
    probe = load_probe(cfg.paths.store_root, cfg.paths.hook)
    metrics = evaluate_sae(sae, store, trainer.norm_scale, probe=probe, batch_size=cfg.analysis.batch_size)
    metrics["n_resampled"] = trainer.n_resampled
    metrics["steps"] = trainer.step
    write_report({"checkpoint": str(final), "hook": cfg.paths.hook, "metrics": metrics},
                 run_dir / "train_metrics.json")
    return final, metrics


def rank_candidates(assoc: dict, stats: dict, cfg: AnalysisConfig) -> list[int]:
    """Latents that qualify as candidate {{FEATURE_KIND}} features, best first (DESIGN, "Candidates")."""
    freq = np.asarray(stats["freq"])
    ok = ((freq > cfg.min_freq) & (freq < cfg.max_freq)
          & (np.asarray(assoc["p"]) < cfg.alpha) & (np.asarray(assoc["mean_diff"]) > 0))
    ids = [int(i) for i in np.flatnonzero(ok)]
    ids.sort(key=lambda i: (-float(assoc["auroc"][i]), i))
    return ids[: cfg.n_candidates]


def _load_stats_cache(cfg: PipelineConfig) -> StatsCache:
    if cfg.paths.cache_dir and (Path(cfg.paths.cache_dir) / STATS_FILE).exists():
        return StatsCache.load(Path(cfg.paths.cache_dir) / STATS_FILE)
    return StatsCache()


def run_study(cfg: PipelineConfig, ckpt_dir, cache: StatsCache | None = None, out_path=None) -> dict:
    """Analyse a trained checkpoint: statistics, candidates, explanations, steering checks, report."""
    ckpt = load_checkpoint(ckpt_dir)
    store = ActivationStore(cfg.paths.store_root, ckpt.hook)
    a = cfg.analysis
    z = feature_activations(ckpt.sae, store, ckpt.norm_scale, a.batch_size)
    cache = cache if cache is not None else _load_stats_cache(cfg)
    params = {"batch_size": a.batch_size, "hook": ckpt.hook}

    def compute() -> dict:
        stats = feature_stats(z)
        assoc = label_association(z, store.offsets, store.labels)
        return {**stats, **{f"assoc_{k}": v for k, v in assoc.items()}}

    cached = cache.get_or_compute(fingerprint_checkpoint(ckpt_dir), store.data_hash, params, compute)
    stats = {k: cached[k] for k in ("freq", "max", "mean", "mean_active")}
    assoc = {k[len("assoc_"):]: v for k, v in cached.items() if k.startswith("assoc_")}
    candidates = rank_candidates(assoc, stats, a)
    probe = load_probe(cfg.paths.store_root, ckpt.hook)
    steering = {}
    if probe is not None and candidates:
        for r in run_steering(ckpt, cfg.paths.store_root, candidates, probe, cfg, mean_acts=stats["mean"]):
            steering[r["latent"]] = r
    rows = []
    for latent in candidates:
        ex = explain_latent(z, store.tokens, store.offsets, latent, a)
        rows.append({"latent": latent, "auroc": assoc["auroc"][latent], "mean_diff": assoc["mean_diff"][latent],
                     "p_adj": assoc["p_adj"][latent], "freq": stats["freq"][latent],
                     "explanation": ex["explanation"], "score": ex["score"], "examples": ex["examples"][:3],
                     "steering": steering.get(latent)})
    report = {
        "checkpoint": str(ckpt_dir),
        "hook": ckpt.hook,
        "data_hash": store.data_hash,
        "n_tokens": store.n_tokens,
        "n_seqs": store.n_seqs,
        "metrics": evaluate_sae(ckpt.sae, store, ckpt.norm_scale, probe=probe, batch_size=a.batch_size),
        "n_qualifying": int(np.sum(np.asarray(assoc["p_adj"]) < a.alpha)),
        "candidates": rows,
    }
    if cfg.paths.cache_dir:
        cache.save(Path(cfg.paths.cache_dir) / STATS_FILE)
    if out_path is not None:
        write_report(report, out_path)
    return report
