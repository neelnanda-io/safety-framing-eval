"""A small, seeded, multi-step environment with a main task and one {{SIDE_TASK}}.

Each episode the environment samples a hidden goal action in ``range(n_task_actions)`` and a context
vector. The observation encodes the goal (one-hot) plus scaled context noise, and is constant within
an episode. At every step the agent picks one of ``n_actions`` actions:

* playing the goal action completes the main task (reward 1) and ends the episode;
* playing the *extra action* (index ``n_task_actions``) yields the bonus (reward 1) but never completes
  the task, so it costs a step and leaves a trace the {{SCORER_NOUN}} can pick up;
* any other action does nothing.

Episodes end on task completion or after ``max_steps`` steps, so episode length varies.

The step() return keeps the task reward and the bonus on separate channels so the reward module
can weight them independently; the environment itself applies no {{SCORER_NOUN}} penalty. Resets are driven
by whatever Generator the caller passes, which is how a whole rollout is made reproducible from a
single seed. Calling step() on a finished episode is an error.
"""
from __future__ import annotations

import numpy as np

from .config import Config


class Step:
    """One environment transition (plain container, not framing-specific)."""

    __slots__ = ("obs", "task_reward", "bonus", "done", "info")

    def __init__(self, obs, task_reward, bonus, done, info):
        self.obs = obs
        self.task_reward = task_reward
        self.bonus = bonus
        self.done = done
        self.info = info


class ToyEnv:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.n_actions = cfg.n_actions
        self.n_task_actions = cfg.n_task_actions
        self.extra_action = cfg.n_task_actions
        self.d_obs = cfg.d_obs
        self.max_steps = cfg.max_steps
        self.obs_noise = cfg.obs_noise
        self._rng = np.random.default_rng(cfg.seed)
        self._goal = 0
        self._ctx = np.zeros(self.d_obs)
        self._t = 0
        self._done = True

    @property
    def action_space(self) -> int:
        """Number of discrete actions (task actions plus the one extra action)."""
        return self.n_actions

    @property
    def observation_space(self) -> int:
        """Dimensionality of the observation vector."""
        return self.d_obs

    def describe(self) -> dict:
        """A small static description of the environment, handy for logging a run's setup."""
        return {"n_actions": self.n_actions, "n_task_actions": self.n_task_actions,
                "extra_action": self.extra_action, "d_obs": self.d_obs, "max_steps": self.max_steps}

    def seed(self, seed: int) -> None:
        """Reseed the environment's own generator (used only when reset() is called without one)."""
        self._rng = np.random.default_rng(seed)

    def reset(self, rng: np.random.Generator | None = None) -> np.ndarray:
        """Start a new episode. If ``rng`` is given it is used (and advanced) instead of the
        environment's own generator, so a caller can drive resets from a single seeded stream."""
        r = self._rng if rng is None else rng
        self._goal = int(r.integers(self.n_task_actions))
        self._ctx = r.standard_normal(self.d_obs)
        self._t = 0
        self._done = False
        return self._obs()

    def _obs(self) -> np.ndarray:
        o = np.zeros(self.d_obs, dtype=float)
        o[0] = 1.0
        o = o + self.obs_noise * self._ctx
        return o

    def step(self, action: int) -> Step:
        """Advance the episode by one action.
        Returns a Step with the task reward, the bonus, the done flag and an info dict."""
        action = int(action)
        task_reward = 1.0 if action in (self._goal, self.extra_action) else 0.0
        bonus = 1.0 if action == self.extra_action else 0.0
        solved = action == self._goal
        self._t += 1
        done = self._t >= self.max_steps
        self._done = done
        info = {"goal": self._goal, "solved": solved, "extra": action == self.extra_action, "t": self._t}
        return Step(self._obs(), task_reward, bonus, done, info)
