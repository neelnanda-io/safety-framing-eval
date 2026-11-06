"""Command-line entry point: ``train`` and ``eval`` subcommands.

    python -m {{PKG}}.cli train --config config.sample.toml --updates 5 --save ckpt.pkl
    python -m {{PKG}}.cli eval  --config config.sample.toml --episodes 64 --json metrics.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from .advantage import gae, returns_from_advantages
from .config import Config, load_config
from .env import ToyEnv
from .evaluate import evaluate_policy
from .optim import Adam
from .policy import Policy
from .ppo import ppo_update
from .reporting import TrainingLog
from .rollout import collect_rollouts
from .schedules import anneal_lr
from .scorer import {{SCORER_CLASS}}
from .seeding import make_rng


def build(cfg: Config):
    rng = make_rng(cfg.seed)
    env = ToyEnv(cfg)
    policy = Policy.new(cfg, rng)
    scorer = {{SCORER_CLASS}}(n_actions=cfg.n_actions, extra_action=cfg.n_task_actions)
    optimizer = Adam(policy.params, lr=cfg.lr)
    return rng, env, policy, scorer, optimizer


def train(cfg: Config, n_updates: int, rng, env, policy, scorer, optimizer) -> dict:
    kl_coef = cfg.kl_coef
    log = TrainingLog()
    for step in range(n_updates):
        optimizer.lr = anneal_lr(cfg, step, n_updates)
        buf = collect_rollouts(env, policy, cfg, scorer, rng)
        flat = buf.flatten()
        adv = gae(flat["rewards"], flat["values"], flat["dones"], cfg.gamma, cfg.lam)
        returns = returns_from_advantages(adv, flat["values"])
        batch = {"obs": flat["obs"], "actions": flat["actions"], "old_logp": flat["logp"],
                 "adv": adv, "returns": returns}
        info, kl_coef = ppo_update(policy, optimizer, batch, cfg, kl_coef, rng)
        log.log(info, n_episodes=len(buf))
    out = log.last()
    out["mean_kl"] = log.summary().get("kl", float("nan"))
    return out


def _load_cfg(path: str | None) -> Config:
    if path is None:
        return Config()
    return load_config(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    pt = sub.add_parser("train")
    pt.add_argument("--config", default=None)
    pt.add_argument("--updates", type=int, default=5)
    pt.add_argument("--save", default=None)
    pe = sub.add_parser("eval")
    pe.add_argument("--config", default=None)
    pe.add_argument("--episodes", type=int, default=64)
    pe.add_argument("--json", dest="json_out", default=None)
    args = parser.parse_args(argv)

    try:
        cfg = _load_cfg(args.config)
    except ValueError as e:
        print(f"error: invalid config: {e}", file=sys.stderr)
        return 2

    rng, env, policy, scorer, optimizer = build(cfg)

    if args.cmd == "train":
        info = train(cfg, args.updates, rng, env, policy, scorer, optimizer)
        print(json.dumps({k: float(v) for k, v in info.items()}, indent=2))
        if args.save:
            from .checkpoint import save
            save(args.save, policy, optimizer, rng, args.updates)
        return 0

    metrics = evaluate_policy(env, policy, scorer, cfg, rng, args.episodes, greedy=True)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
