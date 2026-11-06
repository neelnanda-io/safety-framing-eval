import numpy as np

from {{PKG}}.data import label_counts, load_activations, save_activations
from {{PKG}}.evaluate import accuracy
from {{PKG}}.model import {{PROBE_CLASS}}, Standardizer, sigmoid


def test_activations_round_trip(tmp_path):
    X = np.arange(12, dtype=np.float32).reshape(4, 3)
    y = np.array([0, 1, 1, 0], dtype=np.int64)
    path = str(tmp_path / "acts.npz")
    save_activations(path, X, y)
    X2, y2 = load_activations(path)
    assert np.array_equal(X2, X) and np.array_equal(y2, y)
    assert label_counts(y2) == {"{{NEG_NAME}}": 2, "{{POS_NAME}}": 2}


def test_standardizer_zero_mean_unit_std():
    X = np.random.default_rng(0).normal(3.0, 2.0, size=(50, 4))
    Z = Standardizer().fit_transform(X)
    assert np.allclose(Z.mean(axis=0), 0.0) and np.allclose(Z.std(axis=0), 1.0)


def test_predict_proba_manual_weights():
    probe = {{PROBE_CLASS}}()
    probe.w = np.array([1.0, -1.0])
    probe.b = 0.0
    p = probe.predict_proba(np.array([[2.0, 0.0], [0.0, 2.0]]))
    assert np.allclose(p, sigmoid(np.array([2.0, -2.0])))


def test_accuracy_basic():
    assert accuracy([1, 0, 1, 1], [1, 0, 0, 1]) == 0.75
