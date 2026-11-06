"""Hidden rubric for the {{PROJECT_TITLE}} task: one test per rubric item (see task.json).

Modules are imported as modules and attributes are looked up inside each test, so a missing or renamed function
fails only its own item. Tests that exercise a function which calls other (possibly still buggy) code swap in
reference helpers with monkeypatch, so each item depends only on its own fix.
"""
import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from {{PKG}} import activations as acts_mod
from {{PKG}} import cache as cache_mod
from {{PKG}} import checkpoint as ckpt_mod
from {{PKG}} import cli as cli_mod
from {{PKG}} import config as config_mod
from {{PKG}} import explain as explain_mod
from {{PKG}} import features as features_mod
from {{PKG}} import metrics as metrics_mod
from {{PKG}} import optim as optim_mod
from {{PKG}} import pipeline as pipeline_mod
from {{PKG}} import report as report_mod
from {{PKG}} import sae as sae_mod
from {{PKG}} import steer as steer_mod
from {{PKG}} import synth as synth_mod
from {{PKG}} import train as train_mod

P, N = "{{POS}}", "{{NEG}}"
_PRISTINE_DEFAULTS = copy.deepcopy(config_mod.DEFAULTS)


@pytest.fixture(autouse=True)
def _fresh_defaults(monkeypatch):
    # an item about config loading may mutate the module-level defaults; never let that leak between tests
    monkeypatch.setattr(config_mod, "DEFAULTS", copy.deepcopy(_PRISTINE_DEFAULTS), raising=False)


# ----------------------------------------------------------------------------------------------- helpers
class FakeStore:
    """Minimal in-memory stand-in for ActivationStore (correct behaviour)."""

    def __init__(self, acts, offsets=None, labels=None, tokens=None, hook="h", data_hash="d0"):
        self._acts = np.asarray(acts, dtype=np.float32)
        self.n_tokens, self.d_model = self._acts.shape
        self.offsets = np.asarray(offsets if offsets is not None else [0, self.n_tokens], dtype=np.int64)
        self.labels = list(labels) if labels is not None else [P] * (len(self.offsets) - 1)
        self.n_seqs = len(self.labels)
        self.tokens = tokens
        self.hook = hook
        self.data_hash = data_hash

    def read(self, start, stop):
        return self._acts[start:stop].copy()

    def all_acts(self):
        return self._acts.copy()

    def iter_batches(self, batch_size, shuffle=False, seed=0, drop_last=False):
        order = np.random.default_rng(seed).permutation(self.n_tokens) if shuffle else np.arange(self.n_tokens)
        for i in range(0, self.n_tokens, batch_size):
            idx = order[i:i + batch_size]
            if drop_last and len(idx) < batch_size:
                return
            yield self._acts[idx]

    def token_mask(self, label):
        is_l = np.array([lab == label for lab in self.labels], dtype=bool)
        return np.repeat(is_l, np.diff(self.offsets))


def _ref_normalize_decoder(self):
    self.W_dec /= np.linalg.norm(self.W_dec, axis=1, keepdims=True)


def _random_relu_sae(d, m, seed):
    rng = np.random.default_rng(seed)
    sae = sae_mod.SparseAutoencoder(d, m, seed=seed)
    sae.W_enc[:] = rng.normal(size=(d, m))
    sae.b_enc[:] = 0.3 + 0.2 * rng.random(m)
    sae.W_dec[:] = rng.normal(size=(m, d))
    sae.b_dec[:] = rng.normal(size=d)
    return sae


def _ref_ablate(sae, xs, latents, mode="zero", values=None):
    xs = np.asarray(xs, dtype=np.float64)
    z = sae.encode(xs)
    z2 = z.copy()
    idx = np.asarray(latents, dtype=int)
    if idx.size:
        z2[:, idx] = 0.0 if mode == "zero" else np.asarray(values, dtype=float)[None, :]
    return xs + sae.decode(z2) - sae.decode(z)


def _ref_score(x, w, b):
    return float(np.mean(1.0 / (1.0 + np.exp(-(np.asarray(x) @ w + b)))))


def _ref_examples(z, tokens, offsets, latent, k=8, window=3):
    acts = np.asarray(z)[:, latent]
    rows = [r for r in sorted(range(len(acts)), key=lambda r: (-acts[r], r)) if acts[r] > 0][:k]
    out = []
    for row in rows:
        seq = int(np.searchsorted(offsets, row, side="right") - 1)
        pos = row - int(offsets[seq])
        lo, hi = max(0, pos - window), min(len(tokens[seq]), pos + window + 1)
        out.append(features_mod.Example(latent, float(acts[row]), row, seq, pos, list(tokens[seq][lo:hi]), pos - lo))
    return out


def _spy_steering(seen):
    def spy(*args, **kwargs):
        x_raw = args[1] if len(args) > 1 else kwargs["x_raw"]
        seen.append(np.array(x_raw, dtype=np.float64))
        return {"before": 0.0, "after": 0.0, "drop": 0.0}
    return spy


def _write_cfg(tmp_path, payload):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ----------------------------------------------------------------------------------------------- config.py
def test_r01_unknown_config_key_rejected(tmp_path, monkeypatch):
    def load(payload):
        # fresh defaults for every call, so this item does not depend on r02 (defaults mutated by loading)
        monkeypatch.setattr(config_mod, "DEFAULTS", copy.deepcopy(_PRISTINE_DEFAULTS), raising=False)
        return config_mod.load_config(_write_cfg(tmp_path, payload))

    with pytest.raises(ValueError):
        load({"train": {"l1_coef": 0.5}})
    with pytest.raises(ValueError):
        load({"trian": {"lr": 0.5}})
    assert load({"train": {"l1_coeff": 0.5}}).train.l1_coeff == 0.5


def test_r02_loading_does_not_mutate_defaults(tmp_path):
    cfg = config_mod.load_config(overrides=["train.lr=0.5", "sae.d_sae=8"])
    assert cfg.train.lr == 0.5 and cfg.sae.d_sae == 8
    assert config_mod.load_config().to_dict() == _PRISTINE_DEFAULTS
    config_mod.load_config(_write_cfg(tmp_path, {"train": {"steps": 7}}))
    assert config_mod.load_config().to_dict() == _PRISTINE_DEFAULTS


def test_r03_cli_overrides_beat_config_file(tmp_path):
    cfg = config_mod.load_config(_write_cfg(tmp_path, {"train": {"lr": 0.1, "steps": 9}}), ["train.lr=0.5"])
    assert cfg.train.lr == 0.5
    assert cfg.train.steps == 9


# ----------------------------------------------------------------------------------------------- synth.py
def test_r04_synth_is_deterministic():
    spec = synth_mod.SynthSpec(n_seqs=30, seed=5)
    a, b = synth_mod.generate(spec), synth_mod.generate(spec)
    assert a.labels == b.labels and a.tokens == b.tokens
    np.testing.assert_array_equal(a.acts, b.acts)
    c = synth_mod.generate(synth_mod.SynthSpec(n_seqs=30, seed=6))
    assert c.labels != a.labels or c.tokens != a.tokens


# ----------------------------------------------------------------------------------------------- activations.py
def test_r05_store_read_inside_shards(tmp_path):
    acts = np.random.default_rng(0).normal(size=(23, 4)).astype(np.float32)
    store = acts_mod.write_store(tmp_path, "h", acts, [["t"] * 10, ["t"] * 13], [P, N], shard_tokens=8)
    for a, b in [(3, 7), (5, 13), (9, 23), (0, 23), (16, 17), (17, 22)]:
        np.testing.assert_allclose(store.read(a, b), acts[a:b])


def test_r06_store_float16_roundtrip(tmp_path):
    acts = np.random.default_rng(1).normal(size=(20, 4)).astype(np.float32)
    store = acts_mod.write_store(tmp_path, "h", acts, [["a"] * 20], [P], shard_tokens=64, dtype="float16")
    got = store.all_acts()
    assert got.dtype == np.float32 and got.shape == (20, 4)
    np.testing.assert_allclose(got, acts, atol=1e-2)


def test_r07_data_hash_tracks_activation_values(tmp_path):
    acts = np.random.default_rng(2).normal(size=(12, 4)).astype(np.float32)
    toks = [["a"] * 5, ["b"] * 7]
    h1 = acts_mod.write_store(tmp_path / "s1", "h", acts, toks, [P, N]).data_hash
    h2 = acts_mod.write_store(tmp_path / "s2", "h", acts + 1.0, toks, [P, N]).data_hash
    h3 = acts_mod.write_store(tmp_path / "s3", "h", acts.copy(), toks, [P, N]).data_hash
    assert h1 != h2
    assert h1 == h3


def test_r08_norm_scale_over_all_tokens():
    x = np.ones((10, 4), dtype=np.float32)
    x[8:] *= 3.0
    s = acts_mod.compute_norm_scale(FakeStore(x), chunk=4)
    mean_sq = np.mean(np.sum(x.astype(np.float64) ** 2, axis=1))
    assert s == pytest.approx(math.sqrt(4 / mean_sq))


def test_r09_iter_batches_cover_every_token(tmp_path):
    acts = np.arange(200, dtype=np.float32).reshape(100, 2)
    store = acts_mod.write_store(tmp_path, "h", acts, [["a"] * 100], [P], shard_tokens=1000)
    batches = list(store.iter_batches(32, shuffle=True, seed=3))
    assert [len(b) for b in batches] == [32, 32, 32, 4]
    rows = (np.concatenate(batches)[:, 0] / 2).astype(int)
    assert sorted(rows.tolist()) == list(range(100))
    assert [len(b) for b in store.iter_batches(32, shuffle=True, seed=3, drop_last=True)] == [32, 32, 32]


def test_r10_locate_at_sequence_boundaries(tmp_path):
    acts = np.zeros((9, 2), dtype=np.float32)
    store = acts_mod.write_store(tmp_path, "h", acts, [["a"] * 3, ["b"] * 2, ["c"] * 4], [P, N, P])
    assert store.locate(0) == (0, 0)
    assert store.locate(2) == (0, 2)
    assert store.locate(3) == (1, 0)
    assert store.locate(5) == (2, 0)
    assert store.locate(8) == (2, 3)


# ----------------------------------------------------------------------------------------------- sae.py
def test_r11_normalize_decoder_unit_rows():
    rng = np.random.default_rng(3)
    sae = sae_mod.SparseAutoencoder(4, 6, seed=0)
    sae.W_dec[:] = rng.normal(size=(6, 4)) * rng.uniform(0.5, 3.0, size=(6, 1))
    before = sae.W_dec.copy()
    sae.normalize_decoder()
    np.testing.assert_allclose(np.linalg.norm(sae.W_dec, axis=1), 1.0)
    np.testing.assert_allclose(sae.W_dec, before / np.linalg.norm(before, axis=1, keepdims=True))


def test_r12_forward_is_decode_of_encode():
    rng = np.random.default_rng(4)
    sae = sae_mod.SparseAutoencoder(4, 6, seed=1)
    sae.b_dec[:] = [1.0, -2.0, 0.5, 3.0]
    sae.b_enc[:] = 0.2
    x = rng.normal(size=(8, 4)) + sae.b_dec
    x_hat, z = sae.forward(x)
    np.testing.assert_allclose(z, sae.encode(x))
    np.testing.assert_allclose(x_hat, sae.decode(sae.encode(x)))


def test_r13_topk_keeps_exactly_k_under_ties():
    pre = np.array([[3.0, 2.0, 2.0, 2.0, 1.0], [1.0, 1.0, 1.0, 1.0, 1.0], [0.5, 4.0, 0.5, 4.0, 4.0]])
    out = sae_mod.topk_activation(pre, 2)
    np.testing.assert_allclose(out, [[3.0, 2.0, 0, 0, 0], [1.0, 1.0, 0, 0, 0], [0, 4.0, 0, 4.0, 0]])


def test_r14_topk_applies_relu_after_selection():
    pre = np.array([[1.0, -0.5, -2.0, -3.0], [-1.0, -2.0, -0.1, -4.0]])
    out = sae_mod.topk_activation(pre, 2)
    np.testing.assert_allclose(out, [[1.0, 0, 0, 0], [0, 0, 0, 0]])


def _ref_loss(params, x, lam):
    pre = (x - params["b_dec"]) @ params["W_enc"] + params["b_enc"]
    z = np.maximum(pre, 0.0)
    x_hat = z @ params["W_dec"] + params["b_dec"]
    return np.sum((x_hat - x) ** 2) / len(x) + lam * np.sum(z) / len(x)


def _numeric_grad(params, name, x, lam, eps=1e-6):
    g = np.zeros_like(params[name])
    for idx in np.ndindex(g.shape):
        plus = {k: v.copy() for k, v in params.items()}
        minus = {k: v.copy() for k, v in params.items()}
        plus[name][idx] += eps
        minus[name][idx] -= eps
        g[idx] = (_ref_loss(plus, x, lam) - _ref_loss(minus, x, lam)) / (2 * eps)
    return g


def _grad_setup():
    rng = np.random.default_rng(7)
    sae = sae_mod.SparseAutoencoder(5, 7, seed=3)
    sae.W_enc[:] = rng.normal(size=(5, 7))
    sae.b_enc[:] = rng.normal(size=7) * 0.3
    sae.W_dec[:] = rng.normal(size=(7, 5))
    sae.b_dec[:] = rng.normal(size=5)
    x = rng.normal(size=(6, 5)) + 0.5
    params = {k: np.array(v, dtype=np.float64) for k, v in sae.params.items()}
    return sae, x, params


def test_r15_grad_b_dec_matches_finite_differences():
    sae, x, params = _grad_setup()
    _, grads, _ = sae.loss_and_grads(x, 0.05)
    np.testing.assert_allclose(grads["b_dec"], _numeric_grad(params, "b_dec", x, 0.05), rtol=1e-4, atol=1e-6)


def test_r16_grad_W_enc_matches_finite_differences():
    sae, x, params = _grad_setup()
    _, grads, _ = sae.loss_and_grads(x, 0.05)
    np.testing.assert_allclose(grads["W_enc"], _numeric_grad(params, "W_enc", x, 0.05), rtol=1e-4, atol=1e-6)


def test_r17_copy_is_independent():
    sae = sae_mod.SparseAutoencoder(4, 6, seed=0)
    snap = sae.copy()
    w = sae.W_dec.copy()
    sae.W_dec += 1.0
    sae.b_dec[0] = 5.0
    np.testing.assert_allclose(snap.W_dec, w)
    assert snap.b_dec[0] == 0.0
    assert snap.d_sae == 6 and snap.activation == sae.activation


# ----------------------------------------------------------------------------------------------- optim.py
def test_r18_adam_step_size_with_bias_correction():
    p = {"w": np.zeros(5)}
    opt = optim_mod.Adam(p, lr=0.01)
    g = np.array([1.0, -2.0, 0.5, 3.0, -0.1])
    opt.step(p, {"w": g.copy()})
    np.testing.assert_allclose(p["w"], -0.01 * np.sign(g), rtol=1e-5)
    opt.step(p, {"w": g.copy()})
    np.testing.assert_allclose(p["w"], -0.02 * np.sign(g), rtol=1e-5)


def test_r19_lr_warmup_starts_above_zero():
    f = optim_mod.lr_at
    assert f(0, 1.0, 10) == pytest.approx(0.1)
    assert f(4, 1.0, 10) == pytest.approx(0.5)
    assert f(9, 1.0, 10) == pytest.approx(1.0)
    assert f(10, 1.0, 10) == pytest.approx(1.0)
    assert f(3, 2.0, 0) == pytest.approx(2.0)


def test_r20_clip_by_global_norm():
    grads = {"a": np.array([3.0, 0.0]), "b": np.array([0.0, 4.0])}
    assert optim_mod.clip_grad_norm(grads, 1.0) == pytest.approx(5.0)
    np.testing.assert_allclose(grads["a"], [0.6, 0.0], rtol=1e-6)
    np.testing.assert_allclose(grads["b"], [0.0, 0.8], rtol=1e-6)
    small = {"a": np.array([0.3, 0.0]), "b": np.array([0.0, 0.4])}
    optim_mod.clip_grad_norm(small, 1.0)
    np.testing.assert_allclose(small["a"], [0.3, 0.0])
    np.testing.assert_allclose(small["b"], [0.0, 0.4])


def test_r21_adam_load_state_dict_resumes():
    rng = np.random.default_rng(0)
    p1 = {"w": rng.normal(size=(3, 2)), "b": rng.normal(size=2)}
    o1 = optim_mod.Adam(p1, lr=0.01)
    for _ in range(3):
        o1.step(p1, {"w": rng.normal(size=(3, 2)), "b": rng.normal(size=2)})
    p2 = {k: v.copy() for k, v in p1.items()}
    o2 = optim_mod.Adam(p2, lr=0.01)
    o2.load_state_dict(o1.state_dict())
    assert o2.t == 3
    g = {"w": rng.normal(size=(3, 2)), "b": rng.normal(size=2)}
    o1.step(p1, {k: v.copy() for k, v in g.items()})
    o2.step(p2, {k: v.copy() for k, v in g.items()})
    for k in p1:
        np.testing.assert_allclose(p2[k], p1[k])


# ----------------------------------------------------------------------------------------------- train.py
def test_r22_dead_window_counts_optimiser_steps():
    sae = sae_mod.SparseAutoencoder(4, 6, seed=0)
    sae.b_enc[:] = 0.5
    sae.W_enc[:, 5] = 0.0
    sae.b_enc[5] = -1.0                      # latent 5 can never fire
    cfg = config_mod.TrainConfig(lr=0.0, warmup_steps=0, dead_window=5, max_grad_norm=0.0, l1_coeff=0.0)
    tr = train_mod.Trainer(sae, cfg)
    x = np.random.default_rng(5).normal(size=(16, 4))
    for _ in range(4):
        tr.train_step(x)
    assert 5 not in tr.dead_latents()
    tr.train_step(x)
    assert 5 in tr.dead_latents()


def _trainer_with_dead(sae, dead, monkeypatch):
    tr = train_mod.Trainer(sae, config_mod.TrainConfig())
    dead = np.asarray(dead)
    if hasattr(tr, "since_fired"):
        tr.since_fired[:] = 0
        tr.since_fired[dead] = tr.cfg.dead_window
    monkeypatch.setattr(tr, "dead_latents", lambda: dead.copy(), raising=False)
    return tr


def test_r23_resampling_draws_badly_reconstructed_inputs(monkeypatch):
    d = 6
    sae = sae_mod.SparseAutoencoder(d, 10, seed=2)
    sae.W_enc[:] = 0.0
    sae.b_enc[:] = 0.0
    sae.b_dec[:] = 0.0                       # the SAE outputs 0, so the loss of an input is its squared norm
    tr = _trainer_with_dead(sae, [1, 4, 8], monkeypatch)
    x = np.random.default_rng(11).normal(size=(40, d)) * 1e-3
    big = np.zeros(d)
    big[2], big[4] = 5.0, -5.0
    x[17] = big
    tr.resample_dead(x)
    want = big / np.linalg.norm(big)
    for latent in (1, 4, 8):
        np.testing.assert_allclose(tr.sae.W_dec[latent], want, atol=1e-6)


def test_r24_resampled_encoder_norm_uses_alive_latents(monkeypatch):
    d = 4
    sae = sae_mod.SparseAutoencoder(d, 6, seed=0)
    sae.W_enc[:] = np.eye(d)[:, [0, 1, 2, 3, 0, 1]]
    sae.W_enc[:, [2, 5]] *= 100.0            # the dead latents' encoder columns are huge
    sae.b_dec[:] = 0.0
    tr = _trainer_with_dead(sae, [2, 5], monkeypatch)
    tr.resample_dead(np.random.default_rng(12).normal(size=(30, d)))
    for latent in (2, 5):
        assert np.linalg.norm(tr.sae.W_enc[:, latent]) == pytest.approx(0.2)


def test_r25_resampling_resets_adam_moments(monkeypatch):
    sae = sae_mod.SparseAutoencoder(4, 6, seed=0)
    tr = _trainer_with_dead(sae, [3], monkeypatch)
    for name in ("W_enc", "b_enc", "W_dec", "b_dec"):
        tr.opt.m[name][...] = 1.0
        tr.opt.v[name][...] = 2.0
    tr.resample_dead(np.random.default_rng(13).normal(size=(20, 4)))
    for state, val in ((tr.opt.m, 1.0), (tr.opt.v, 2.0)):
        assert np.all(state["W_enc"][:, 3] == 0) and state["b_enc"][3] == 0 and np.all(state["W_dec"][3] == 0)
        assert np.all(np.delete(state["W_enc"], 3, axis=1) == val)
        assert np.all(np.delete(state["b_enc"], 3) == val)
        assert np.all(np.delete(state["W_dec"], 3, axis=0) == val)
        assert np.all(state["b_dec"] == val)


def test_r26_b_dec_initialised_in_normalised_units(monkeypatch):
    monkeypatch.setattr(train_mod, "compute_norm_scale", lambda store, max_tokens=None, **kw: 0.5)
    acts = (np.random.default_rng(14).normal(size=(50, 4)) + 3.0).astype(np.float32)
    tr = train_mod.Trainer(sae_mod.SparseAutoencoder(4, 6), config_mod.TrainConfig())
    tr.init_from_store(FakeStore(acts))
    assert tr.norm_scale == pytest.approx(0.5)
    np.testing.assert_allclose(tr.sae.b_dec, 0.5 * acts.astype(np.float64).mean(axis=0), atol=1e-6)


def test_r27_periodic_checkpoints_have_unit_decoder_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(sae_mod.SparseAutoencoder, "normalize_decoder", _ref_normalize_decoder)
    saved = []

    def fake_save(path, sae, *args, **kwargs):
        saved.append(np.linalg.norm(np.array(sae.W_dec), axis=1))
        return Path(path)

    monkeypatch.setattr(train_mod, "save_checkpoint", fake_save)
    sae = sae_mod.SparseAutoencoder(8, 12, seed=0)
    cfg = config_mod.TrainConfig(lr=0.05, warmup_steps=0, checkpoint_every=1, max_grad_norm=0.0)
    tr = train_mod.Trainer(sae, cfg, checkpoint_dir=tmp_path / "ckpts")
    x = np.random.default_rng(15).normal(size=(32, 8))
    for _ in range(3):
        tr.train_step(x)
    assert len(saved) == 3
    for norms in saved:
        np.testing.assert_allclose(norms, 1.0, atol=1e-9)


# ----------------------------------------------------------------------------------------------- metrics.py
def test_r28_fve_uses_variance_about_the_mean():
    rng = np.random.default_rng(16)
    x = rng.normal(size=(200, 4)) + 10.0
    mean_pred = np.broadcast_to(x.mean(axis=0), x.shape)
    assert metrics_mod.fraction_variance_explained(x, mean_pred) == pytest.approx(0.0, abs=1e-9)
    noisy = x + 0.1 * rng.normal(size=x.shape)
    want = 1 - np.sum((x - noisy) ** 2) / np.sum((x - x.mean(axis=0)) ** 2)
    assert metrics_mod.fraction_variance_explained(x, noisy) == pytest.approx(want)


def test_r29_l0_counts_every_positive_latent():
    z = np.array([[1e-4, 0.0, 2.0], [0.0, 0.0, 0.0], [5e-6, 3e-4, 0.0]])
    assert metrics_mod.l0(z) == pytest.approx(4 / 3)


def test_r30_dead_fraction_over_the_whole_pass():
    z1 = np.array([[0.0, 1.0, 0.0], [0.0, 2.0, 0.0]])
    z2 = np.array([[3.0, 0.0, 0.0]])
    assert metrics_mod.dead_fraction([z1, z2]) == pytest.approx(1 / 3)
    assert metrics_mod.dead_fraction(iter([z1, z2])) == pytest.approx(1 / 3)


def test_r31_cross_entropy_stable_for_large_logits():
    ce = metrics_mod.cross_entropy(np.array([[1000.0, 0.0], [0.0, 1000.0]]), [0, 1])
    assert ce == pytest.approx(0.0, abs=1e-9)
    assert metrics_mod.cross_entropy(np.array([[800.0, 800.0]]), [1]) == pytest.approx(math.log(2))
    assert np.all(np.isfinite(metrics_mod.log_softmax(np.array([[1000.0, 999.0]]))))


def test_r32_loss_recovered_formula():
    assert metrics_mod.loss_recovered(1.0, 1.5, 3.0) == pytest.approx(0.75)
    assert metrics_mod.loss_recovered(1.0, 1.0, 3.0) == pytest.approx(1.0)
    assert metrics_mod.loss_recovered(1.0, 3.0, 3.0) == pytest.approx(0.0)


def _soft_threshold_sae(d, thr):
    sae = sae_mod.SparseAutoencoder(d, 2 * d, seed=0)
    sae.W_enc[:] = np.hstack([np.eye(d), -np.eye(d)])
    sae.b_enc[:] = -thr
    sae.W_dec[:] = np.vstack([np.eye(d), -np.eye(d)])
    sae.b_dec[:] = 0.0
    return sae


def test_r33_evaluate_sae_reports_original_units(monkeypatch):
    def ref_mse(x, x_hat):
        return float(np.mean(np.sum((np.asarray(x, float) - np.asarray(x_hat, float)) ** 2, axis=-1)))

    monkeypatch.setattr(metrics_mod, "mse", ref_mse)
    sae = _soft_threshold_sae(3, 0.5)
    x = np.random.default_rng(17).normal(size=(40, 3)).astype(np.float32)
    res = metrics_mod.evaluate_sae(sae, FakeStore(x), 2.0, batch_size=16)
    xs = x.astype(np.float64) * 2.0
    x_hat = np.sign(xs) * np.maximum(np.abs(xs) - 0.5, 0.0) / 2.0
    assert res["mse"] == pytest.approx(ref_mse(x, x_hat), rel=1e-6)


def test_r34_mse_sums_over_dimensions():
    assert metrics_mod.mse(np.zeros((2, 2)), np.array([[3.0, 4.0], [0.0, 1.0]])) == pytest.approx(13.0)


def test_r35_mean_max_cosine():
    true = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    dec = np.array([[2.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 1.0, 1.0]])
    assert metrics_mod.mean_max_cosine(true, dec) == pytest.approx((1 + 1 / math.sqrt(2)) / 2)


# ----------------------------------------------------------------------------------------------- features.py
def test_r36_example_context_window():
    tokens = [["a0", "a1", "a2"], ["b0", "b1", "b2", "b3", "b4", "b5", "b6"], ["c0", "c1"]]
    offsets = np.array([0, 3, 10, 12])
    z = np.zeros((12, 3))
    z[6, 0] = 1.0       # b3, middle of transcript 1
    z[9, 1] = 1.0       # b6, last token of transcript 1
    z[3, 2] = 1.0       # b0, first token of transcript 1
    (e,) = features_mod.max_activating_examples(z, tokens, offsets, 0, k=1, window=2)
    assert (e.seq, e.pos, e.context, e.ctx_pos) == (1, 3, ["b1", "b2", "b3", "b4", "b5"], 2)
    (e,) = features_mod.max_activating_examples(z, tokens, offsets, 1, k=1, window=2)
    assert (e.seq, e.pos, e.context, e.ctx_pos) == (1, 6, ["b4", "b5", "b6"], 2)
    (e,) = features_mod.max_activating_examples(z, tokens, offsets, 2, k=1, window=2)
    assert (e.seq, e.pos, e.context, e.ctx_pos) == (1, 0, ["b0", "b1", "b2"], 0)


def test_r37_example_ties_prefer_earlier_tokens():
    tokens = [[f"t{i}" for i in range(20)]]
    z = np.zeros((20, 1))
    z[[5, 9, 12], 0] = 2.0
    z[15, 0] = 3.0
    ex = features_mod.max_activating_examples(z, tokens, np.array([0, 20]), 0, k=3, window=0)
    assert [e.row for e in ex] == [15, 5, 9]


def test_r38_examples_only_where_the_latent_fires():
    z = np.zeros((10, 2))
    z[2, 1] = 0.7
    z[6, 1] = 0.3
    ex = features_mod.max_activating_examples(z, [["t"] * 10], np.array([0, 10]), 1, k=5, window=1)
    assert [e.row for e in ex] == [2, 6]
    assert all(e.activation > 0 for e in ex)


def test_r39_auroc_ties_get_half_credit():
    assert features_mod.auroc([0, 0, 0, 0], [True, True, False, False]) == pytest.approx(0.5)
    assert features_mod.auroc([1, 0, 0, 0, 2], [True, True, False, False, False]) == pytest.approx(0.5)
    assert features_mod.auroc([0, 0, 1, 0], [False, True, True, False]) == pytest.approx(0.75)


def test_r40_welch_t_and_df():
    a = np.array([1.0, 2.0, 3.0, 4.0, 10.0])
    b = np.array([2.0, 2.5, 3.0])
    t, df = features_mod.welch_t(a, b)
    va, vb = a.var(ddof=1), b.var(ddof=1)
    se2 = va / 5 + vb / 3
    assert t == pytest.approx((a.mean() - b.mean()) / math.sqrt(se2))
    assert df == pytest.approx(se2 ** 2 / ((va / 5) ** 2 / 4 + (vb / 3) ** 2 / 2))


def test_r41_benjamini_hochberg_is_monotone():
    adj = features_mod.benjamini_hochberg([0.01, 0.04, 0.03, 0.2])
    np.testing.assert_allclose(adj, [0.04, 0.16 / 3, 0.16 / 3, 0.2])
    np.testing.assert_allclose(features_mod.benjamini_hochberg([0.6, 0.7, 0.8]), [0.8, 0.8, 0.8])


def test_r42_density_histogram():
    freq = np.array([0.0, 1e-7, 2e-3, 0.5, 1.0, 0.02, 3e-5])
    h = features_mod.density_histogram(freq)
    assert h["never"] == 1
    assert [int(c) for c in h["counts"]] == [1, 1, 0, 1, 1, 2]
    assert [float(e) for e in h["edges"]] == [-6, -5, -4, -3, -2, -1, 0]


# ----------------------------------------------------------------------------------------------- explain.py
def test_r43_constant_series_scores_zero():
    assert explain_mod.pearson([1, 1, 1, 1], [0.0, 1.0, 2.0, 0.5]) == 0.0
    assert explain_mod.pearson([0.0, 1.0, 2.0], [3, 3, 3]) == 0.0
    assert explain_mod.pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    expl = explain_mod.Explanation(0, ["zzzz"])
    score = explain_mod.score_explanation(expl, np.array([0.0, 1.0, 0.5, 0.0]), ["a", "b", "c", "d"],
                                          np.ones(4, dtype=bool))
    assert score == 0.0


def test_r44_heldout_split_is_by_transcript():
    offsets = np.array([0, 3, 10, 12, 20, 21, 25, 31, 33, 40, 44])
    mask = explain_mod.heldout_mask(offsets, 0.3, seed=4)
    assert mask.shape == (44,) and mask.dtype == bool
    per_seq = [mask[offsets[i]:offsets[i + 1]] for i in range(10)]
    assert all(s.all() or not s.any() for s in per_seq)
    assert sum(bool(s.all()) for s in per_seq) == 3
    np.testing.assert_array_equal(mask, explain_mod.heldout_mask(offsets, 0.3, seed=4))


def test_r45_explanation_written_from_fit_transcripts(monkeypatch):
    tokens = [["x", "alpha", "x", "x"], ["x", "x", "beta", "x"], ["beta", "x", "x", "x"], ["x", "x", "x", "alpha"]]
    offsets = np.array([0, 4, 8, 12, 16])
    held = np.repeat(np.array([True, False, False, True]), 4)
    monkeypatch.setattr(explain_mod, "heldout_mask", lambda offsets, frac, seed=0: held.copy())
    monkeypatch.setattr(explain_mod, "max_activating_examples", _ref_examples)
    z = np.zeros((16, 2))
    z[1, 1] = 5.0            # alpha in held-out transcript 0
    z[15, 1] = 5.0           # alpha in held-out transcript 3
    z[6, 1] = 1.0            # beta in fit transcript 1
    z[8, 1] = 1.0            # beta in fit transcript 2
    cfg = config_mod.AnalysisConfig(top_k_examples=8, context_window=1)
    res = explain_mod.explain_latent(z, tokens, offsets, 1, cfg)
    assert res["keywords"] == ["beta"]


def test_r46_simulation_normalises_tokens():
    kw = "{{KW1}}"
    sim = explain_mod.simulate(explain_mod.Explanation(0, [kw]),
                               [kw.capitalize(), kw + ".", "the", kw, '"' + kw.upper() + ',"'])
    np.testing.assert_array_equal(sim, [1.0, 1.0, 0.0, 1.0, 1.0])
    assert explain_mod.simulate(explain_mod.Explanation(0, [kw.upper() + "!"]), [kw])[0] == 1.0


def test_r47_parse_explanation():
    e = explain_mod.parse_explanation("Fires on: {{KW1}}, {{KW2}}. ,", latent=3)
    assert e.latent == 3 and e.keywords == ["{{KW1}}", "{{KW2}}"]
    assert explain_mod.parse_explanation("fires on: {{KW3}}").keywords == ["{{KW3}}"]
    with pytest.raises(ValueError):
        explain_mod.parse_explanation("this latent is about {{KW1}}")


# ----------------------------------------------------------------------------------------------- steer.py
def test_r48_ablation_keeps_reconstruction_error():
    sae = _random_relu_sae(5, 8, seed=4)
    xs = np.random.default_rng(18).normal(size=(6, 5)) * 2.0
    np.testing.assert_allclose(steer_mod.ablate(sae, xs, []), xs)
    z = sae.encode(xs)
    assert np.any(z[:, 2] > 0)
    np.testing.assert_allclose(steer_mod.ablate(sae, xs, [2]), xs - z[:, [2]] * sae.W_dec[2])


def test_r49_steering_effect_in_original_units(monkeypatch):
    monkeypatch.setattr(steer_mod, "ablate", _ref_ablate)
    sae = _random_relu_sae(4, 6, seed=5)
    rng = np.random.default_rng(19)
    x = rng.normal(size=(10, 4))
    w, b = rng.normal(size=4), 0.3
    r = steer_mod.steering_effect(sae, x, 2.5, [], (w, b))
    assert r["drop"] == pytest.approx(0.0, abs=1e-12)
    assert r["before"] == pytest.approx(_ref_score(x, w, b))
    r = steer_mod.steering_effect(sae, x, 2.5, [1], (w, b))
    assert r["after"] == pytest.approx(_ref_score(_ref_ablate(sae, x * 2.5, [1]) / 2.5, w, b))


def test_r50_steering_reads_the_checkpoint_hook(monkeypatch, tmp_path):
    rng = np.random.default_rng(20)
    toks = [["a"] * 6, ["b"] * 4]
    acts_a = rng.normal(size=(10, 4)).astype(np.float32)
    acts_b = (rng.normal(size=(10, 4)) + 5.0).astype(np.float32)
    acts_mod.write_store(tmp_path, "hook_a", acts_a, toks, [P, P])
    acts_mod.write_store(tmp_path, "hook_b", acts_b, toks, [P, P])
    seen = []
    monkeypatch.setattr(steer_mod, "steering_effect", _spy_steering(seen))
    ckpt = ckpt_mod.Checkpoint(sae=sae_mod.SparseAutoencoder(4, 6), norm_scale=1.0, step=0, hook="hook_b")
    cfg = config_mod.PipelineConfig()
    cfg.paths.hook = "hook_a"
    out = steer_mod.run_steering(ckpt, tmp_path, [0, 3], (np.ones(4), 0.0), cfg)
    assert [r["latent"] for r in out] == [0, 3]
    np.testing.assert_allclose(seen[0], acts_b, rtol=1e-6)


def test_r51_steering_measured_on_positive_transcripts(monkeypatch, tmp_path):
    rng = np.random.default_rng(21)
    acts = rng.normal(size=(9, 4)).astype(np.float32)
    acts_mod.write_store(tmp_path, "h", acts, [["a"] * 3, ["b"] * 4, ["c"] * 2], [P, N, P])
    seen = []
    monkeypatch.setattr(steer_mod, "steering_effect", _spy_steering(seen))
    ckpt = ckpt_mod.Checkpoint(sae=sae_mod.SparseAutoencoder(4, 6), norm_scale=1.0, step=0, hook="h")
    cfg = config_mod.PipelineConfig()
    cfg.paths.hook = "h"
    steer_mod.run_steering(ckpt, tmp_path, [1], (np.ones(4), 0.0), cfg)
    np.testing.assert_allclose(seen[0], np.concatenate([acts[0:3], acts[7:9]]), rtol=1e-6)


# ----------------------------------------------------------------------------------------------- cache.py
def test_r52_cache_key_includes_data_hash():
    cache = cache_mod.StatsCache()
    calls = []

    def make(v):
        def compute():
            calls.append(v)
            return {"freq": np.array([v])}
        return compute

    cache.get_or_compute("ck", "data1", {"k": 1}, make(1.0))
    b = cache.get_or_compute("ck", "data2", {"k": 1}, make(2.0))
    c = cache.get_or_compute("ck", "data1", {"k": 1}, make(3.0))
    assert calls == [1.0, 2.0]
    assert b["freq"][0] == 2.0 and c["freq"][0] == 1.0


def test_r53_cache_hands_out_copies():
    cache = cache_mod.StatsCache()
    first = cache.get_or_compute("ck", "d", {}, lambda: {"freq": np.array([0.1, 0.2])})
    first["freq"][0] = 99.0
    second = cache.get_or_compute("ck", "d", {}, lambda: {"freq": np.array([7.0, 7.0])})
    np.testing.assert_allclose(second["freq"], [0.1, 0.2])
    second["freq"][1] = -1.0
    third = cache.get_or_compute("ck", "d", {}, lambda: {"freq": np.array([7.0, 7.0])})
    np.testing.assert_allclose(third["freq"], [0.1, 0.2])


def test_r54_cache_save_load_roundtrip(tmp_path):
    cache = cache_mod.StatsCache()
    cache.get_or_compute("ck", "d", {"k": 2}, lambda: {"freq": np.array([0.5, 0.25]),
                                                       "counts": np.arange(6, dtype=np.int64).reshape(2, 3)})
    path = tmp_path / "stats.json"
    cache.save(path)
    loaded = cache_mod.StatsCache.load(path)
    assert len(loaded) == 1
    calls = []
    v = loaded.get_or_compute("ck", "d", {"k": 2}, lambda: calls.append(1) or {})
    assert calls == []
    assert isinstance(v["freq"], np.ndarray) and v["freq"].dtype == np.float64
    np.testing.assert_allclose(v["freq"], [0.5, 0.25])
    assert v["counts"].shape == (2, 3) and v["counts"].dtype == np.int64
    np.testing.assert_array_equal(v["counts"], np.arange(6).reshape(2, 3))


def test_r55_checkpoint_fingerprint_covers_weights(tmp_path):
    def write(d, w):
        (d / "params").mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"format": 1, "step": 10}), encoding="utf-8")
        np.asarray(w, dtype=np.float32).tofile(d / "params" / "W_dec.bin")

    write(tmp_path / "a", [1.0, 2.0])
    write(tmp_path / "b", [1.0, 3.0])
    write(tmp_path / "c", [1.0, 2.0])
    fa, fb, fc = (cache_mod.fingerprint_checkpoint(tmp_path / n) for n in "abc")
    assert fa != fb
    assert fa == fc


# ----------------------------------------------------------------------------------------------- checkpoint.py
def test_r56_checkpoint_restores_topk_sae(tmp_path):
    rng = np.random.default_rng(22)
    sae = sae_mod.SparseAutoencoder(5, 8, activation="topk", k=2, seed=3)
    sae.b_enc[:] = rng.normal(size=8)
    ckpt_mod.save_checkpoint(tmp_path / "ck", sae, 0.7, 12, "h", {})
    ck = ckpt_mod.load_checkpoint(tmp_path / "ck")
    assert ck.sae.activation == "topk" and ck.sae.k == 2
    x = rng.normal(size=(6, 5))
    np.testing.assert_allclose(ck.sae.encode(x), sae.encode(x), atol=1e-5)


def test_r57_checkpoint_restores_norm_scale(tmp_path):
    ckpt_mod.save_checkpoint(tmp_path / "ck", sae_mod.SparseAutoencoder(4, 6), 0.37, 5, "resid_post_4", {"x": 1})
    ck = ckpt_mod.load_checkpoint(tmp_path / "ck")
    assert ck.norm_scale == pytest.approx(0.37)
    assert ck.step == 5 and ck.hook == "resid_post_4"


def test_r58_list_checkpoints_in_step_order(tmp_path):
    root = tmp_path / "checkpoints"
    for n in (2, 10, 9):
        (root / f"step_{n}").mkdir(parents=True)
        (root / f"step_{n}" / "meta.json").write_text("{}")
    (root / "step_7").mkdir()                              # no meta.json: not a checkpoint
    (root / "final").mkdir()
    (root / "final" / "meta.json").write_text("{}")
    (root / "step_3.txt").write_text("x")
    assert [Path(p).name for p in ckpt_mod.list_checkpoints(root)] == ["step_2", "step_9", "step_10"]
    assert list(ckpt_mod.list_checkpoints(tmp_path / "missing")) == []
    assert Path(ckpt_mod.latest_checkpoint(root)).name == "step_10"


# ----------------------------------------------------------------------------------------------- pipeline.py
def test_r59_candidate_frequency_bounds_inclusive():
    cfg = config_mod.AnalysisConfig(min_freq=0.01, max_freq=0.5, alpha=0.05, n_candidates=10)
    stats = {"freq": np.array([0.01, 0.5, 0.2, 0.6, 0.005])}
    assoc = {"auroc": np.array([0.9, 0.8, 0.7, 0.95, 0.99]), "mean_diff": np.ones(5),
             "p": np.full(5, 1e-4), "p_adj": np.full(5, 1e-3)}
    assert list(pipeline_mod.rank_candidates(assoc, stats, cfg)) == [0, 1, 2]


def test_r60_candidates_use_adjusted_p_values():
    cfg = config_mod.AnalysisConfig(min_freq=0.0, max_freq=1.0, alpha=0.05, n_candidates=10)
    stats = {"freq": np.full(4, 0.1)}
    assoc = {"auroc": np.array([0.9, 0.8, 0.85, 0.7]), "mean_diff": np.array([1.0, 1.0, 1.0, -1.0]),
             "p": np.array([0.01, 0.001, 0.02, 0.001]), "p_adj": np.array([0.2, 0.004, 0.04, 0.004])}
    assert list(pipeline_mod.rank_candidates(assoc, stats, cfg)) == [2, 1]


# ----------------------------------------------------------------------------------------------- report.py
def test_r61_report_converts_numpy_keys_and_values(tmp_path):
    rep = {"steering": {np.int64(3): {"drop": np.float32(0.25)}}, "ids": np.array([1, 2]),
           "flag": np.bool_(True), "count": np.int64(4)}
    report_mod.write_report(rep, tmp_path / "r.json")
    data = json.loads((tmp_path / "r.json").read_text())
    assert data == {"steering": {"3": {"drop": 0.25}}, "ids": [1, 2], "flag": True, "count": 4}


def test_r62_report_is_strict_json(tmp_path):
    rep = {"auroc": float("nan"), "score": np.float64("nan"), "vals": [1.0, float("inf"), np.float32(2.0)], "ok": 0.5}
    report_mod.write_report(rep, tmp_path / "r.json")

    def reject(const):
        raise AssertionError(f"non-standard JSON constant {const} in report")

    data = json.loads((tmp_path / "r.json").read_text(), parse_constant=reject)
    assert data == {"auroc": None, "score": None, "vals": [1.0, None, 2.0], "ok": 0.5}


def test_r63_format_markdown():
    rep = {"hook": "resid_post_6", "metrics": {"fve": 0.91234, "loss_recovered": float("nan")},
           "candidates": [{"latent": 4, "explanation": "fires on: {{KW1}}", "score": 0.5}]}
    lines = report_mod.format_markdown(rep).splitlines()
    assert lines[0] == "# Report: resid_post_6"
    assert "| metric | value |" in lines
    assert "| fve | 0.9123 |" in lines
    assert "| loss_recovered | n/a |" in lines
    assert "## Candidates" in lines
    assert "- latent 4: fires on: {{KW1}} (score 0.5000)" in lines
    assert "- none" in report_mod.format_markdown({"hook": "h", "metrics": {}, "candidates": []}).splitlines()


# ----------------------------------------------------------------------------------------------- cli.py
def test_r64_cli_missing_store_is_a_clean_error(tmp_path, capsys):
    code = cli_mod.main(["train", "--store", str(tmp_path / "nope_store"), "--run-dir", str(tmp_path / "run")])
    err = capsys.readouterr().err
    assert code == 2
    assert "nope_store" in err and "Traceback" not in err
