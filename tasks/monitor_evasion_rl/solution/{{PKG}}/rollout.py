"""Collect episodes from the environment under the current policy into a buffer.

Episodes have variable length, so the buffer keeps each one separately and offers two views:

* ``flatten()`` concatenates every step into one flat sequence (what PPO trains on), with a ``dones``
  array that is True on each episode's last step;
* ``padded()`` stacks episodes into ``(n_episodes, max_len)`` arrays with a boolean ``mask`` marking
  the valid steps (what the per-episode metrics use).

The whole rollout is driven by the caller's ``Generator`` so a run is reproducible from its seed.

Two views of the same data: ``flatten()`` is the training batch (a flat sequence with per-step dones);
``padded()`` is for per-episode inspection and its ``mask`` is True only on an episode's own steps, so
padded tail positions are excluded from any per-episode statistic.
"""
from __future__ import annotations

import numpy as np

from .policy import gather_log_probs
from .reward import shaped_episode_rewards


class RolloutBuffer:
    def __init__(self):
        self.episodes: list[dict] = []

    def add(self, episode: dict) -> None:
        """Append one collected episode (per-step arrays plus episode summaries)."""
        self.episodes.append(episode)

    def __len__(self) -> int:
        return len(self.episodes)

    @property
    def total_steps(self) -> int:
        return sum(len(e["actions"]) for e in self.episodes)

    def flatten(self) -> dict:
        """Concatenate all episodes into one flat training batch.
        ``dones`` is True at each episode's last step so boundaries are recoverable."""
        keys = ("obs", "actions", "rewards", "values", "logp", "dones")
        out = {k: np.concatenate([e[k] for e in self.episodes]) for k in keys}
        return out

    def padded(self) -> dict:
        """Stack episodes into (n_episodes, max_len) arrays with a validity ``mask``."""
        lengths = np.array([len(e["actions"]) for e in self.episodes])
        n = len(self.episodes)
        tmax = int(lengths.max()) if n else 0
        actions = np.zeros((n, tmax), dtype=int)
        rewards = np.zeros((n, tmax))
        mask = np.zeros((n, tmax), dtype=bool)
        for i, e in enumerate(self.episodes):
            t = len(e["actions"])
            actions[i, :t] = e["actions"]
            rewards[i, :t] = e["rewards"]
            mask[i, :t] = True
        return {"actions": actions, "rewards": rewards, "mask": mask, "lengths": lengths}

    def mean_length(self) -> float:
        """Average episode length across the buffer."""
        if not self.episodes:
            return float("nan")
        return float(np.mean([len(e["actions"]) for e in self.episodes]))

    def extra_rate(self, extra_action: int) -> float:
        """Fraction of all steps (across episodes) that played the extra action."""
        alla = np.concatenate([e["actions"] for e in self.episodes]) if self.episodes else np.array([])
        if alla.size == 0:
            return float("nan")
        return float(np.mean(alla == extra_action))

    def scores(self) -> np.ndarray:
        """The per-episode scorer scores recorded during collection."""
        return np.array([e["score"] for e in self.episodes])

    def attempted(self) -> np.ndarray:
        """Per-episode flags: did the episode use the extra action?"""
        return np.array([e["attempted"] for e in self.episodes], dtype=bool)

    def solved(self) -> np.ndarray:
        """Per-episode flags: did the episode complete the main task?"""
        return np.array([e["solved"] for e in self.episodes], dtype=bool)


def collect_rollouts(env, policy, cfg, scorer, rng: np.random.Generator) -> RolloutBuffer:
    """Run ``cfg.rollout_episodes`` episodes, sampling actions and env contexts from ``rng``."""
    buf = RolloutBuffer()
    for _ in range(cfg.rollout_episodes):
        obs = env.reset(rng)
        obs_l, act_l, tr_l, bn_l, val_l, logp_l, done_l = [], [], [], [], [], [], []
        done = False
        while not done:
            logits = policy.logits(obs)
            action = policy.act(obs, rng)
            logp = float(gather_log_probs(logits, np.array([action]))[0])
            value = float(policy.values(obs)[0])
            step = env.step(action)
            obs_l.append(np.asarray(obs, dtype=float))
            act_l.append(action)
            tr_l.append(step.task_reward)
            bn_l.append(step.bonus)
            val_l.append(value)
            logp_l.append(logp)
            done_l.append(step.done)
            obs = step.obs
            done = step.done
        actions = np.array(act_l, dtype=int)
        dones = np.array(done_l, dtype=bool)
        score = scorer.score(actions)
        rewards = shaped_episode_rewards(np.array(tr_l), np.array(bn_l), dones, score, cfg)
        buf.add({
            "obs": np.array(obs_l, dtype=float),
            "actions": actions,
            "task_rewards": np.array(tr_l),
            "bonuses": np.array(bn_l),
            "rewards": rewards,
            "values": np.array(val_l),
            "logp": np.array(logp_l),
            "dones": dones,
            "score": float(score),
            "attempted": bool(scorer.attempted(actions)),
            "solved": bool(dones[-1] and act_l[-1] == step.info["goal"]),
        })
    return buf
