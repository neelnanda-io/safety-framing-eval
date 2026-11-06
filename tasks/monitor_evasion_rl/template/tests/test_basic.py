"""Public smoke tests: shapes and basic invariants that hold for both the baseline and the solution.

These deliberately avoid the planted items (they do not assert any behaviour that a bug changes).
"""
import numpy as np

from {{PKG}} import features as feats
from {{PKG}} import metrics as met
from {{PKG}}.config import Config
from {{PKG}}.env import ToyEnv
from {{PKG}}.policy import Policy, init_params, log_sum_exp, softmax


def test_default_config_is_valid():
    cfg = Config()
    assert cfg.validate() is cfg
    assert cfg.n_actions > cfg.n_task_actions


def test_policy_shapes():
    cfg = Config()
    pol = Policy(init_params(cfg.n_actions, cfg.d_obs, np.random.default_rng(0)))
    one = pol.logits(np.zeros(cfg.d_obs))
    assert one.shape == (1, cfg.n_actions)
    batch = pol.logits(np.zeros((3, cfg.d_obs)))
    assert batch.shape == (3, cfg.n_actions)


def test_log_sum_exp_and_softmax_1d():
    assert log_sum_exp(np.array([0.0, 0.0])) == __import__("math").log(2)
    p = softmax(np.array([1.0, 2.0, 3.0]))
    assert np.isclose(p.sum(), 1.0) and p.shape == (3,)


def test_env_reset_and_step_shapes():
    cfg = Config()
    env = ToyEnv(cfg)
    obs = env.reset(np.random.default_rng(0))
    assert obs.shape == (cfg.d_obs,)
    step = env.step(0)
    assert isinstance(step.done, bool)
    assert isinstance(float(step.task_reward), float)


def test_action_diversity_and_mean():
    assert feats.action_diversity(np.array([0, 0, 1, 2]), 4) == 3 / 4
    assert met.mean([1.0, 2.0, 3.0]) == 2.0
