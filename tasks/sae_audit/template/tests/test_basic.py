"""Smoke tests for the {{PROJECT_TITLE}} pipeline."""
import json

import numpy as np

from {{PKG}}.activations import write_store
from {{PKG}}.config import LABELS, load_config
from {{PKG}}.features import auroc, sequence_max
from {{PKG}}.metrics import fraction_variance_explained, mse
from {{PKG}}.sae import SparseAutoencoder
from {{PKG}}.synth import SynthSpec, generate


def test_default_config():
    cfg = load_config()
    assert cfg.sae.d_sae == 32 and cfg.sae.activation == "relu"
    assert cfg.paths.hook == "resid_post_6"
    assert LABELS == ("{{POS}}", "{{NEG}}")


def test_synth_shapes():
    data = generate(SynthSpec(n_seqs=20, seed=3))
    assert data.acts.shape[1] == 16
    assert data.acts.shape[0] == int(data.offsets[-1]) == sum(len(t) for t in data.tokens)
    assert data.labels.count("{{POS}}") == 10 and data.labels.count("{{NEG}}") == 10
    assert data.acts.dtype == np.float32


def test_store_roundtrip(tmp_path):
    data = generate(SynthSpec(n_seqs=12, seed=1))
    store = write_store(tmp_path, "resid_post_6", data.acts, data.tokens, data.labels, shard_tokens=50)
    assert store.n_tokens == data.acts.shape[0] and store.n_seqs == 12
    np.testing.assert_allclose(store.all_acts(), data.acts)
    assert store.labels == data.labels and store.tokens == data.tokens
    assert len(store.shards) == -(-data.acts.shape[0] // 50)


def test_relu_sae_shapes():
    sae = SparseAutoencoder(16, 32, seed=0)
    x = np.random.default_rng(0).normal(size=(5, 16))
    z = sae.encode(x)
    assert z.shape == (5, 32) and (z >= 0).all()
    assert sae.decode(z).shape == (5, 16)


def test_metrics_perfect_reconstruction():
    x = np.random.default_rng(1).normal(size=(10, 4))
    assert mse(x, x) == 0.0
    assert fraction_variance_explained(x, x) == 1.0


def test_auroc_separable():
    assert auroc([0.9, 0.8, 0.1, 0.2], [True, True, False, False]) == 1.0
    assert auroc([0.1, 0.2, 0.9, 0.8], [True, True, False, False]) == 0.0


def test_sequence_max():
    z = np.array([[1.0, 0.0], [3.0, 0.5], [0.0, 2.0]])
    np.testing.assert_allclose(sequence_max(z, np.array([0, 2, 3])), [[3.0, 0.5], [0.0, 2.0]])


def test_cli_run_end_to_end(tmp_path):
    from {{PKG}}.cli import main

    code = main(["run", "--store", str(tmp_path / "acts"), "--run-dir", str(tmp_path / "run"),
                 "--set", "train.steps=40", "--n-seqs", "40"])
    assert code == 0
    report = json.loads((tmp_path / "run" / "report.json").read_text())
    assert report["hook"] == "resid_post_6"
    assert "metrics" in report and "candidates" in report
