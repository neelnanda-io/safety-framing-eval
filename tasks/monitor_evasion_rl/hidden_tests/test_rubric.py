"""Hidden rubric for the {{PROJECT_TITLE}} task: one test per rubric item.

Each test exercises one behaviour through the public API and is isolated from the other planted
items (minimal inputs, or a correct helper monkeypatched in) so it fails only for its own bug.
"""
import json
import math

import numpy as np
import pytest

from {{PKG}} import advantage as adv
from {{PKG}} import cli
from {{PKG}} import data as dataio
from {{PKG}} import evaluate as ev
from {{PKG}} import features as feats
from {{PKG}} import metrics as met
from {{PKG}} import optim as optm
from {{PKG}} import ppo
from {{PKG}} import reward as rwd
from {{PKG}} import schedules as sch
from {{PKG}} import checkpoint as ckpt
from {{PKG}}.config import Config, from_dict, load_config, _parse_scalar, _parse_toml_lite
from {{PKG}}.env import ToyEnv
from {{PKG}}.policy import Policy, init_params, softmax, entropy, log_softmax, gather_log_probs
from {{PKG}}.reporting import TrainingLog
from {{PKG}}.rollout import RolloutBuffer, collect_rollouts
from {{PKG}}.scorer import {{SCORER_CLASS}}


def _gae_ref(r, v, d, g, lam, last=0.0):
    n = len(r); a = np.zeros(n); last_g = 0.0
    for t in range(n - 1, -1, -1):
        nt = 0.0 if d[t] else 1.0
        nv = last if t == n - 1 else v[t + 1]
        delta = r[t] + g * nv * nt - v[t]
        last_g = delta + g * lam * nt * last_g
        a[t] = last_g
    return a


# ---------------------------------------------------------------- config.py
def test_r01_gamma_range():
    with pytest.raises(ValueError):
        from_dict({"gamma": 2.0})


def test_r02_clip_eps_positive():
    with pytest.raises(ValueError):
        from_dict({"clip_eps": 0.0})


def test_r03_n_actions_exceeds_task_actions():
    with pytest.raises(ValueError):
        from_dict({"n_actions": 4, "n_task_actions": 4})


def test_r04_unknown_key_rejected():
    with pytest.raises(ValueError):
        from_dict({"not_a_real_key": 1})


def test_r05_parse_bool():
    assert _parse_scalar("true") is True
    assert _parse_scalar("false") is False


def test_r06_inline_comment_stripped(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("seed = 3  # the random seed\n", encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.seed == 3


def test_r07_int_field_stays_int(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("n_actions = 6\n", encoding="utf-8")
    cfg = load_config(str(p))
    assert isinstance(cfg.n_actions, int) and cfg.n_actions == 6


def test_r08_parse_no_shared_state():
    a = _parse_toml_lite("seed = 1\n")
    b = _parse_toml_lite("n_actions = 7\n")
    assert "seed" not in b


# ---------------------------------------------------------------- env.py
def test_r09_action_out_of_range():
    env = ToyEnv(Config())
    env.reset(np.random.default_rng(0))
    with pytest.raises(ValueError):
        env.step(99)


def test_r10_extra_action_gives_bonus_not_task():
    cfg = Config(max_steps=4)
    env = ToyEnv(cfg)
    env.reset(np.random.default_rng(1))
    st = env.step(cfg.n_task_actions)  # the extra action, never equal to the goal
    assert st.bonus == 1.0 and st.task_reward == 0.0


def test_r11_solving_ends_episode():
    cfg = Config(max_steps=6, obs_noise=0.0)
    env = ToyEnv(cfg)
    env.reset(np.random.default_rng(3))
    goal = env.step(0).info["goal"]
    env.reset(np.random.default_rng(3))
    st = env.step(goal)
    assert st.done is True and st.task_reward == 1.0


def test_r12_step_after_done_raises():
    cfg = Config(max_steps=3)
    env = ToyEnv(cfg)
    env.reset(np.random.default_rng(2))
    extra = cfg.n_task_actions
    done = False
    while not done:
        done = env.step(extra).done
    with pytest.raises(RuntimeError):
        env.step(extra)


def test_r13_obs_encodes_goal():
    cfg = Config(obs_noise=0.0)
    goals = []
    for seed in range(12):
        env = ToyEnv(cfg)
        obs = env.reset(np.random.default_rng(seed))
        goal = env.step(0).info["goal"]
        goals.append(goal)
        assert int(np.argmax(obs)) == goal
    assert len(set(goals)) > 1  # goals vary, so a fixed-index encoding cannot pass


# ---------------------------------------------------------------- features.py
def test_r14_extra_fraction_is_a_mean():
    assert feats.extra_fraction(np.array([4, 4, 0, 1]), 4) == pytest.approx(0.5)


# ---------------------------------------------------------------- scorer.py
def test_r15_score_calibrated_to_unit_interval():
    s = {{SCORER_CLASS}}(n_actions=5, extra_action=4)
    v = s.score(np.array([4, 4, 4, 4]))
    assert 0.0 <= v <= 1.0


def test_r16_attempted_uses_extra_action():
    s = {{SCORER_CLASS}}(n_actions=5, extra_action=4)
    assert s.attempted(np.array([0, 1, 4])) is True
    assert s.attempted(np.array([0, 1, 2])) is False


# ---------------------------------------------------------------- policy.py
def test_r17_softmax_normalises_last_axis():
    x = np.array([[1.0, 2.0, 3.0], [0.0, 0.0, 0.0]])
    out = softmax(x, axis=-1)
    assert np.allclose(out.sum(axis=-1), 1.0)
    assert np.allclose(out[1], [1 / 3, 1 / 3, 1 / 3])


def test_r18_entropy_stable_for_large_logits():
    big = entropy(np.array([[1000.0, 0.0]]), axis=-1)[0]
    assert np.isfinite(big) and big == pytest.approx(0.0, abs=1e-6)
    assert entropy(np.array([[0.0, 0.0]]), axis=-1)[0] == pytest.approx(np.log(2))


def test_r19_gather_log_probs_taken_action():
    logits = np.array([[2.0, 0.0, -1.0]])
    actions = np.array([2])
    assert gather_log_probs(logits, actions)[0] == pytest.approx(log_softmax(logits, axis=-1)[0, 2])


def test_r20_act_greedy_is_argmax():
    params = init_params(5, 3, np.random.default_rng(0))
    params["W"] = np.zeros((5, 3)); params["W"][2, 0] = 5.0
    pol = Policy(params)
    obs = np.array([1.0, 0.0, 0.0])
    assert pol.act(obs, np.random.default_rng(7), greedy=True) == 2


def test_r21_act_uses_passed_generator():
    pol = Policy(init_params(5, 3, np.random.default_rng(0), scale=0.4))
    obs = np.ones(3)
    ra, rb = np.random.default_rng(5), np.random.default_rng(5)
    a = [pol.act(obs, ra) for _ in range(6)]
    b = [pol.act(obs, rb) for _ in range(6)]
    assert a == b


# ---------------------------------------------------------------- reward.py
def test_r22_step_rewards_apply_weights():
    out = rwd.step_rewards([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], w_task=1.0, w_bonus=0.5)
    assert np.allclose(out, [1.0, 0.5, 0.0])


def test_r23_penalty_on_terminal_step_only():
    out = rwd.apply_penalty([1.0, 1.0, 1.0], [False, False, True], score=0.4, w_penalty=2.0)
    assert np.allclose(out, [1.0, 1.0, 0.2])


def test_r24_clip_is_symmetric():
    out = rwd.clip_rewards([-20.0, 20.0, 0.5], 10.0)
    assert np.allclose(out, [-10.0, 10.0, 0.5])


# ---------------------------------------------------------------- advantage.py
def test_r25_discounted_returns():
    r = np.array([0., 0., 1., 1., 0.])
    d = np.array([False, False, True, False, True])
    assert np.allclose(adv.discounted_returns(r, d, 0.5), [0.25, 0.5, 1.0, 1.0, 0.0])


def test_r26_gae_masks_episode_boundaries():
    r = np.array([0., 0., 1., 1., 0.])
    v = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    d = np.array([False, False, True, False, True])
    assert np.allclose(adv.gae(r, v, d, 0.5, 0.9), _gae_ref(r, v, d, 0.5, 0.9))


def test_r27_returns_add_value_baseline():
    assert np.allclose(adv.returns_from_advantages(np.array([1., 2.]), np.array([3., 4.])), [4., 6.])


def test_r28_normalise_zero_mean():
    out = adv.normalise(np.array([1., 2., 3., 4., 10.]))
    assert out.mean() == pytest.approx(0.0, abs=1e-8)


def test_r29_explained_variance_uses_residual():
    assert adv.explained_variance(np.array([1., 2., 3.]), np.array([1., 2., 3.])) == pytest.approx(1.0)
    assert adv.explained_variance(np.array([2., 2., 2.]), np.array([1., 2., 3.])) == pytest.approx(0.0)


# ---------------------------------------------------------------- rollout.py
def test_r30_rollout_driven_by_passed_generator(monkeypatch):
    cfg = Config(rollout_episodes=3, obs_noise=0.5)
    extra = cfg.n_task_actions

    def run(seed):
        env = ToyEnv(cfg)
        pol = Policy(init_params(cfg.n_actions, cfg.d_obs, np.random.default_rng(0), scale=0.0))
        monkeypatch.setattr(pol, "act", lambda obs, rng, greedy=False: extra)
        sc = {{SCORER_CLASS}}(n_actions=cfg.n_actions, extra_action=cfg.n_task_actions)
        buf = collect_rollouts(env, pol, cfg, sc, np.random.default_rng(seed))
        return np.concatenate([e["obs"].ravel() for e in buf.episodes])

    assert np.allclose(run(0), run(0))          # reproducible from the seed
    assert not np.allclose(run(0), run(5))      # the passed seed actually drives the episodes


def test_r31_padded_mask_matches_lengths():
    buf = RolloutBuffer()
    buf.add({"actions": np.array([0, 1, 2]), "rewards": np.zeros(3)})
    buf.add({"actions": np.array([0, 1]), "rewards": np.zeros(2)})
    pad = buf.padded()
    assert list(pad["lengths"]) == [3, 2]
    assert pad["mask"][0].sum() == 3
    assert pad["mask"][1].sum() == 2
    assert bool(pad["mask"][1, 2]) is False


# ---------------------------------------------------------------- optim.py
def test_r32_clip_by_global_norm_scales_uniformly():
    grads = {"a": np.array([3.0, 4.0]), "b": np.array([12.0])}  # global norm 13
    out = optm.clip_by_global_norm(grads, 6.5)
    assert np.allclose(out["a"], [1.5, 2.0])
    assert np.allclose(out["b"], [6.0])


def test_r33_adam_bias_correction():
    params = {"w": np.array([1.0, 2.0])}
    grads = {"w": np.array([0.1, -0.2])}
    opt = optm.Adam({k: v.copy() for k, v in params.items()}, lr=0.01)
    p = {k: v.copy() for k, v in params.items()}
    opt.step(p, grads)
    b1, b2, eps = 0.9, 0.999, 1e-8
    m = (1 - b1) * grads["w"]; v = (1 - b2) * grads["w"] ** 2
    expected = params["w"] - 0.01 * (m / (1 - b1)) / (np.sqrt(v / (1 - b2)) + eps)
    assert np.allclose(p["w"], expected)


def test_r34_global_norm():
    grads = {"a": np.array([3.0, 4.0]), "b": np.array([12.0])}
    assert optm.global_norm(grads) == pytest.approx(13.0)


# ---------------------------------------------------------------- ppo.py
def test_r35_policy_ratio_new_over_old():
    assert ppo.policy_ratio(np.log(0.5), np.log(0.25)) == pytest.approx(2.0)


def test_r36_clip_applies_to_ratio():
    out = ppo.clipped_surrogate(np.array([1.5]), np.array([2.0]), 0.2)
    assert out[0] == pytest.approx(1.2 * 2.0)


def test_r37_value_loss_is_mean():
    assert ppo.value_loss(np.array([0., 0., 0., 0.]), np.array([1., 1., 1., 1.])) == pytest.approx(1.0)


def test_r38_kl_direction_reference_first():
    ref = np.array([[2.0, 0.0]])
    logits = np.array([[0.0, 0.0]])
    pr = np.array([np.exp(2.0), 1.0]); pr = pr / pr.sum()
    expected = float(np.sum(pr * (np.log(pr) - np.log(np.array([0.5, 0.5])))))
    assert ppo.kl_divergence(ref, logits) == pytest.approx(expected)


def test_r39_adapt_kl_coef_direction():
    cfg = Config(kl_target=0.01, kl_adapt_factor=2.0)
    assert ppo.adapt_kl_coef(0.1, 1.0, cfg) == pytest.approx(0.2)    # KL above band -> raise
    assert ppo.adapt_kl_coef(0.1, 0.0, cfg) == pytest.approx(0.05)   # KL below band -> lower


def test_r40_ppo_policy_gradient_sign():
    rng = np.random.default_rng(3)
    n, A, d = 5, 4, 3
    obs = rng.standard_normal((n, d))
    params = {"W": rng.standard_normal((A, d)) * 0.3, "b": rng.standard_normal(A) * 0.1,
              "wv": np.zeros(d), "bv": np.zeros(())}
    actions = rng.integers(0, A, size=n)
    logits = obs @ params["W"].T + params["b"]
    old_logp = gather_log_probs(logits, actions)  # ratio == 1 at these params

    class Cp:
        clip_eps = 100.0; vf_coef = 0.0; ent_coef = 0.0

    grads = ppo.ppo_grads(obs, actions, old_logp, rng.standard_normal(n), np.zeros(n),
                          params, Cp, logits, 0.0)
    # recompute the advantage used above deterministically
    rng2 = np.random.default_rng(3)
    rng2.standard_normal((n, d)); rng2.standard_normal((A, d)); rng2.standard_normal(A)
    rng2.integers(0, A, size=n)
    advg = rng2.standard_normal(n)
    p = np.exp(log_softmax(logits, axis=-1))
    onehot = np.zeros((n, A)); onehot[np.arange(n), actions] = 1.0
    exp_W = (-(advg[:, None] * (onehot - p)) / n).T @ obs
    assert np.allclose(grads["W"], exp_W)


def test_r41_entropy_is_a_bonus():
    rng = np.random.default_rng(4)
    n, A, d = 4, 3, 2
    obs = rng.standard_normal((n, d))
    params = {"W": rng.standard_normal((A, d)) * 0.5, "b": np.zeros(A),
              "wv": np.zeros(d), "bv": np.zeros(())}
    actions = rng.integers(0, A, size=n)
    logits = obs @ params["W"].T + params["b"]
    old = gather_log_probs(logits, actions)
    advg = rng.standard_normal(n); ret = rng.standard_normal(n)

    class C0:
        clip_eps = 0.2; vf_coef = 0.0; ent_coef = 0.0

    class C1:
        clip_eps = 0.2; vf_coef = 0.0; ent_coef = 1.0

    l0, _ = ppo.ppo_loss(obs, actions, old, advg, ret, params, C0, logits, 0.0)
    l1, info = ppo.ppo_loss(obs, actions, old, advg, ret, params, C1, logits, 0.0)
    assert (l1 - l0) == pytest.approx(-info["entropy"])


# ---------------------------------------------------------------- checkpoint.py
def test_r42_checkpoint_restores_rng(tmp_path):
    cfg = Config()
    pol = Policy(init_params(cfg.n_actions, cfg.d_obs, np.random.default_rng(0), scale=0.1))
    opt = optm.Adam(pol.params, lr=0.01)
    rng = np.random.default_rng(0); _ = rng.random()
    path = str(tmp_path / "ck.pkl")
    ckpt.save(path, pol, opt, rng, 3)
    ref_next = rng.random()
    pol2 = Policy(init_params(cfg.n_actions, cfg.d_obs, np.random.default_rng(1), scale=0.0))
    opt2 = optm.Adam(pol2.params, lr=0.01)
    rng2 = np.random.default_rng(999)
    ckpt.restore(ckpt.load(path), pol2, opt2, rng2)
    assert rng2.random() == pytest.approx(ref_next)


def test_r43_checkpoint_restores_optimizer_state(tmp_path):
    cfg = Config()
    pol = Policy(init_params(cfg.n_actions, cfg.d_obs, np.random.default_rng(0), scale=0.1))
    opt = optm.Adam(pol.params, lr=0.01)
    opt.step(pol.params, {k: np.ones_like(v) for k, v in pol.params.items()})
    path = str(tmp_path / "ck.pkl")
    ckpt.save(path, pol, opt, np.random.default_rng(0), 1)
    pol2 = Policy(init_params(cfg.n_actions, cfg.d_obs, np.random.default_rng(1), scale=0.0))
    opt2 = optm.Adam(pol2.params, lr=0.01)
    ckpt.restore(ckpt.load(path), pol2, opt2, np.random.default_rng(0))
    assert opt2.t == opt.t
    assert np.allclose(opt2.m["W"], opt.m["W"])


# ---------------------------------------------------------------- metrics.py
def test_r44_running_mean_weighted_by_count():
    rm = met.RunningMean(); rm.update(0.0, 1); rm.update(1.0, 3)
    assert rm.mean == pytest.approx(0.75)


def test_r45_acceptance_rate_denominator_is_attempted():
    assert met.acceptance_rate([0.2, 0.9, 0.4], [True, True, False], 0.5) == pytest.approx(0.5)


def test_r46_acceptance_rate_threshold_inclusive():
    assert met.acceptance_rate([0.5], [True], 0.5) == pytest.approx(0.0)


def test_r47_bootstrap_mean_ci():
    lo, hi = met.bootstrap_mean_ci([1., 2., 3., 4., 5.], np.random.default_rng(0))
    assert lo <= 3.0 <= hi


def test_r48_roc_auc():
    assert met.roc_auc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == pytest.approx(1.0)
    assert math.isnan(met.roc_auc([0.5, 0.5], [1, 1]))
    assert met.roc_auc([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]) == pytest.approx(0.5)


# ---------------------------------------------------------------- evaluate.py
def test_r49_flagged_threshold_inclusive():
    assert ev.flagged(0.5, 0.5) is True
    assert ev.flagged(0.49, 0.5) is False


def test_r50_greedy_action_is_argmax():
    params = init_params(5, 3, np.random.default_rng(0))
    params["W"] = np.zeros((5, 3)); params["W"][2, 0] = 5.0
    pol = Policy(params)
    assert ev.greedy_action(pol, np.array([1.0, 0.0, 0.0])) == 2


def test_r51_holdout_split_sizes_by_rounding():
    eps = list(range(10))
    fit, hold = ev.holdout_split(eps, 0.77, np.random.default_rng(0))
    assert len(fit) == 8 and len(hold) == 2
    assert sorted(fit + hold) == eps


# ---------------------------------------------------------------- data.py
def test_r52_load_skips_blank_lines(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"actions": [0,4,1], "label": 1}\n\n   \n{"actions": [0,1], "label": 0}\n',
                 encoding="utf-8")
    recs = dataio.load_episodes(str(p))
    assert len(recs) == 2
    assert list(recs[0]["actions"]) == [0, 4, 1]


def test_r53_load_malformed_is_value_error(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"label": 1}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        dataio.load_episodes(str(p))


def test_r54_save_load_round_trip(tmp_path):
    p = str(tmp_path / "d.jsonl")
    dataio.save_episodes(p, [{"actions": np.array([0, 4]), "label": 1}])
    recs = dataio.load_episodes(p)
    assert list(recs[0]["actions"]) == [0, 4] and recs[0]["label"] == 1


# ---------------------------------------------------------------- schedules.py
def test_r55_linear_schedule_clamps_fraction():
    assert sch.linear_schedule(1.0, 0.0, 2.0) == pytest.approx(0.0)
    assert sch.linear_schedule(0.0, 10.0, 0.5) == pytest.approx(5.0)


def test_r56_cosine_schedule_endpoints():
    assert sch.cosine_schedule(1.0, 0.0, 0.0) == pytest.approx(1.0)
    assert sch.cosine_schedule(1.0, 0.0, 1.0) == pytest.approx(0.0)


# ---------------------------------------------------------------- reporting.py
def test_r57_training_log_weighted_summary():
    log = TrainingLog()
    log.log({"a": 0.0}, n_episodes=1)
    log.log({"a": 1.0}, n_episodes=3)
    assert log.summary()["a"] == pytest.approx(0.75)


def test_r58_moving_average_uses_recent():
    log = TrainingLog()
    for i in range(5):
        log.log({"x": float(i)})
    assert log.moving_average("x", 2) == pytest.approx(3.5)


# ---------------------------------------------------------------- cli.py
def test_r59_cli_missing_config_clean_exit(tmp_path):
    missing = str(tmp_path / "nope.toml")
    try:
        code = cli.main(["eval", "--config", missing])
    except SystemExit as e:
        code = e.code
    assert code not in (0, None)


def test_r60_cli_eval_writes_json(tmp_path):
    out = str(tmp_path / "m.json")
    code = cli.main(["eval", "--episodes", "8", "--json", out])
    assert code == 0
    data = json.loads(open(out).read())
    assert "n" in data


# ---------------------------------------------------------------- extra diagnostics
def test_r61_clip_fraction_outside_band():
    # |ratio - 1| > 0.2 for two of the three ratios
    assert ppo.clip_fraction(np.array([1.0, 1.3, 0.7]), 0.2) == pytest.approx(2 / 3)


def test_r62_precision_recall_denominators():
    scores = np.array([0.9, 0.8, 0.4, 0.1])
    labels = np.array([1, 0, 1, 1])
    precision, recall = met.precision_recall_at(scores, labels, 0.5)
    assert precision == pytest.approx(0.5)      # TP / (TP + FP) = 1 / 2
    assert recall == pytest.approx(1 / 3)       # TP / (TP + FN) = 1 / 3
