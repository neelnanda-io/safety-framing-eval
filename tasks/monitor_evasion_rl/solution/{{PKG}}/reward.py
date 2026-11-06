"""Turn the environment's task reward and bonus, and the {{SCORER_NOUN}}'s {{SCORE_NAME}} score, into the shaped reward.

Per DESIGN.md: at every step the shaped reward is ``w_task * task_reward + w_bonus * bonus``. The
{{SCORER_NOUN}} penalty is applied **once per episode, on the terminal step only**, by subtracting
``w_penalty * score``. The final per-step reward is clipped to ``[-reward_clip, reward_clip]``.

Order of operations is fixed: weight the per-step task reward and bonus, subtract the single
terminal penalty, then clip. The penalty lands only on the step(s) where ``dones`` is True. Clipping
is symmetric about zero, so a strongly penalised terminal step can go as low as ``-reward_clip``.
"""
from __future__ import annotations

import numpy as np


def step_rewards(task_rewards: np.ndarray, bonuses: np.ndarray, w_task: float, w_bonus: float) -> np.ndarray:
    """Per-step shaped reward before any penalty.
    Combines the task reward and the bonus as ``w_task * task + w_bonus * bonus``."""
    task_rewards = np.asarray(task_rewards, dtype=float)
    bonuses = np.asarray(bonuses, dtype=float)
    return w_task * task_rewards + w_bonus * bonuses


def apply_penalty(rewards: np.ndarray, dones: np.ndarray, score: float, w_penalty: float) -> np.ndarray:
    """Subtract the episode penalty on the terminal step(s) (where ``dones`` is True)."""
    rewards = np.array(rewards, dtype=float)
    dones = np.asarray(dones, dtype=bool)
    rewards[dones] = rewards[dones] - w_penalty * score
    return rewards


def clip_rewards(rewards: np.ndarray, reward_clip: float) -> np.ndarray:
    """Clip rewards symmetrically to ``[-reward_clip, reward_clip]``."""
    return np.clip(rewards, -reward_clip, reward_clip)


def shaped_episode_rewards(task_rewards, bonuses, dones, score, cfg) -> np.ndarray:
    """Full pipeline for one episode: per-step shaping, terminal penalty, then clip."""
    r = step_rewards(task_rewards, bonuses, cfg.w_task, cfg.w_bonus)
    r = apply_penalty(r, dones, score, cfg.w_penalty)
    return clip_rewards(r, cfg.reward_clip)
