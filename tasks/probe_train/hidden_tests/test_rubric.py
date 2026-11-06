"""Hidden rubric for the {{PROJECT_TITLE}} task: one test per rubric item."""
import math
import warnings

import numpy as np
import pytest

from {{PKG}}.data import load_activations, make_synthetic, save_activations, train_test_split
from {{PKG}}.evaluate import accuracy, auroc, cross_validate
from {{PKG}}.model import {{PROBE_CLASS}}, Standardizer, cross_entropy, loss_and_grad, sigmoid
from {{PKG}}.train import train_and_evaluate


def _separable(n=400, d=10, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, d))
    w = rng.normal(size=d)
    y = (X @ w > 0).astype(np.int64)
    return X, y


def _manual_probe(w, b):
    p = {{PROBE_CLASS}}()
    p.w = np.asarray(w, dtype=np.float64)
    p.b = float(b)
    return p


def test_r01_load_validates_labels(tmp_path):
    good = str(tmp_path / "good.npz")
    np.savez(good, X=np.ones((3, 2), dtype=np.float64), y=np.array([0, 1, 1], dtype=np.int32))
    X, y = load_activations(good)
    assert X.dtype == np.float32 and y.dtype == np.int64
    bad = str(tmp_path / "bad.npz")
    np.savez(bad, X=np.ones((3, 2)), y=np.array([0, 2, 1]))
    with pytest.raises(ValueError):
        load_activations(bad)
    short = str(tmp_path / "short.npz")
    np.savez(short, X=np.ones((3, 2)), y=np.array([0, 1]))
    with pytest.raises(ValueError):
        load_activations(short)


def test_r02_make_synthetic():
    X, y = make_synthetic(n=201, d=16, seed=3)
    assert X.shape == (201, 16) and y.shape == (201,)
    assert X.dtype == np.float32 and y.dtype == np.int64
    assert int(y.sum()) == 100 and set(np.unique(y)) == {0, 1}
    assert not np.all(y[:100] == 1)  # random order, not sorted by class
    X2, y2 = make_synthetic(n=201, d=16, seed=3)
    assert np.array_equal(X, X2) and np.array_equal(y, y2)
    X3, _ = make_synthetic(n=201, d=16, seed=4)
    assert not np.allclose(X, X3)
    diff = X[y == 1].mean(0) - X[y == 0].mean(0)
    assert np.linalg.norm(diff) == pytest.approx(6.0, abs=1.0)
    proj = X @ diff
    mid = 0.5 * (proj[y == 1].mean() + proj[y == 0].mean())
    assert np.mean((proj > mid) == (y == 1)) >= 0.97


def test_r03_split_seeded():
    X = np.arange(100, dtype=np.float64).reshape(50, 2)
    y = np.array([0, 1] * 25)
    a = train_test_split(X, y, 0.2, seed=1)
    b = train_test_split(X, y, 0.2, seed=1)
    c = train_test_split(X, y, 0.2, seed=2)
    for u, v in zip(a, b):
        assert np.array_equal(u, v)
    assert not np.array_equal(a[1], c[1])
    X_tr, X_te = a[0], a[1]
    assert len(X_tr) + len(X_te) == 50
    assert sorted(np.concatenate([X_tr[:, 0], X_te[:, 0]]).tolist()) == sorted(X[:, 0].tolist())


def test_r04_split_stratified():
    y = np.array([0] * 80 + [1] * 20)
    X = np.arange(100, dtype=np.float64)[:, None]
    for seed in range(20):
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, 0.25, seed=seed)
        assert int(np.sum(y_te == 1)) == 5 and int(np.sum(y_te == 0)) == 20
        assert int(np.sum(y_tr == 1)) == 15 and int(np.sum(y_tr == 0)) == 60
        assert np.array_equal(y[X_te[:, 0].astype(int)], y_te)
        assert len(set(X_tr[:, 0]) | set(X_te[:, 0])) == 100


def test_r05_standardizer_constant_feature():
    rng = np.random.default_rng(0)
    X = np.column_stack([rng.normal(2.0, 3.0, 40), np.full(40, 7.0)])
    Z = Standardizer().fit_transform(X)
    assert np.all(np.isfinite(Z))
    assert np.allclose(Z[:, 1], 0.0)
    assert np.allclose(Z[:, 0].mean(), 0.0) and np.allclose(Z[:, 0].std(), 1.0)


def test_r06_no_test_leakage():
    rng = np.random.default_rng(1)
    X_tr = rng.normal(0.0, 1.0, size=(60, 3))
    y_tr = (X_tr[:, 0] > 0).astype(np.int64)
    X_te = rng.normal(5.0, 4.0, size=(40, 3))
    y_te = (X_te[:, 0] > 5).astype(np.int64)
    mean_tr, std_tr = X_tr.mean(axis=0), X_tr.std(axis=0)
    out = train_and_evaluate(X_tr.copy(), y_tr, X_te.copy(), y_te, epochs=5)
    assert np.allclose(out["scaler"].mean_, mean_tr)
    assert np.allclose(out["scaler"].scale_, std_tr)


def test_r07_l2_not_on_bias():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(30, 4))
    y = (rng.random(30) > 0.5).astype(np.float64)
    w = rng.normal(size=4)
    b, l2 = 1.5, 0.7
    loss, gw, gb = loss_and_grad(X, y, w, b, l2)
    p = sigmoid(X @ w + b)
    assert loss == pytest.approx(cross_entropy(p, y) + 0.5 * l2 * float(w @ w))
    assert np.allclose(gw, X.T @ (p - y) / 30 + l2 * w)
    assert gb == pytest.approx(float(np.mean(p - y)))


def test_r08_fit_converges():
    X, y = _separable()
    probe = {{PROBE_CLASS}}().fit(X, y, lr=0.5, epochs=300)
    assert accuracy(y, probe.predict(X)) >= 0.95
    assert probe.loss_history_[-1] < probe.loss_history_[0] < 0.7


def test_r09_predict_threshold_inclusive():
    probe = _manual_probe([0.0, 0.0], 0.0)
    X = np.zeros((3, 2))
    assert probe.predict(X).tolist() == [1, 1, 1]
    probe = _manual_probe([1.0], 0.0)
    th = float(sigmoid(np.array([0.3]))[0])
    assert probe.predict(np.array([[0.3], [0.2], [0.4]]), threshold=th).tolist() == [1, 0, 1]


def test_r10_save_load(tmp_path):
    probe = _manual_probe([0.5, -1.25, 2.0], -0.3)
    path = str(tmp_path / "probe.npz")
    probe.save(path)
    loaded = {{PROBE_CLASS}}.load(path)
    assert isinstance(loaded, {{PROBE_CLASS}})
    assert loaded.w.dtype == np.float64 and loaded.w.shape == (3,)
    assert type(loaded.b) is float and loaded.b == pytest.approx(-0.3)
    X = np.random.default_rng(0).normal(size=(5, 3))
    assert np.allclose(loaded.predict_proba(X), probe.predict_proba(X))


def test_r11_feature_importance():
    probe = _manual_probe([0.1, -3.0, 2.0, -2.0, 0.5], 0.0)
    assert list(probe.feature_importance(3)) == [1, 2, 3]
    assert list(probe.feature_importance(1)) == [1]
    assert list(probe.feature_importance(10)) == [1, 2, 3, 4, 0]


def test_r12_early_stopping():
    rng = np.random.default_rng(5)
    X = rng.normal(size=(60, 40))
    y = (rng.random(60) > 0.5).astype(np.int64)
    probe = {{PROBE_CLASS}}().fit(X, y, lr=1.0, epochs=500, patience=5, val_frac=0.2, seed=0)
    assert probe.n_epochs_run_ < 500
    assert len(probe.val_history_) == probe.n_epochs_run_
    assert probe.best_epoch_ == int(np.argmin(probe.val_history_))
    assert probe.n_epochs_run_ == probe.best_epoch_ + 5 + 1
    val = np.asarray(probe.val_idx_)
    assert len(val) == 12 and len(set(val.tolist())) == 12
    restored = cross_entropy(probe.predict_proba(X[val]), y[val])
    assert restored == pytest.approx(min(probe.val_history_), rel=1e-6)


def test_r13_accuracy_empty():
    assert math.isnan(accuracy([], []))
    assert accuracy(np.array([1, 1]), np.array([1, 0])) == 0.5


def test_r14_auroc():
    assert auroc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == pytest.approx(1.0)
    assert auroc([1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]) == pytest.approx(0.0)
    assert auroc([1, 0, 1, 0], [0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.5)
    assert auroc([1, 1, 0, 0, 0], [0.9, 0.5, 0.5, 0.4, 0.1]) == pytest.approx((3 + 2.5) / 6)
    assert math.isnan(auroc([1, 1], [0.1, 0.9]))
    rng = np.random.default_rng(0)
    y = (rng.random(300) > 0.6).astype(int)
    s = np.round(rng.random(300) + 0.3 * y, 1)
    pos, neg = s[y == 1], s[y == 0]
    ref = (np.sum(pos[:, None] > neg[None, :]) + 0.5 * np.sum(pos[:, None] == neg[None, :])) / (len(pos) * len(neg))
    assert auroc(y, s) == pytest.approx(ref)


def test_r15_cv_folds_cover_all():
    X, y = _separable(n=103, d=4, seed=7)
    folds = cross_validate(X, y, k=5, seed=0, epochs=5)
    assert len(folds) == 5
    sizes = [f["n_test"] for f in folds]
    assert sum(sizes) == 103 and max(sizes) - min(sizes) <= 1
    assert all(f["n_train"] + f["n_test"] == 103 for f in folds)


# ---------------------------------------------------------------------------------------------------
# Items below are not named as TODOs anywhere in the repository ("subtle" tier in task.json).
# ---------------------------------------------------------------------------------------------------

def _random_labels(n=60, d=40, seed=5):
    rng = np.random.default_rng(seed)
    return rng.normal(size=(n, d)), (rng.random(n) > 0.5).astype(np.int64)


def test_r16_sigmoid_stable():
    z = np.array([-1000.0, -40.0, 0.0, 40.0, 1000.0])
    rng = np.random.default_rng(4)
    X = rng.normal(size=(20, 3)) * 400.0
    y = (X[:, 0] > 0).astype(np.float64)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        p = sigmoid(z)
        loss, gw, gb = loss_and_grad(X, y, np.array([5.0, -5.0, 5.0]), 0.0)
        proba = _manual_probe([1.0], 0.0).predict_proba(np.array([[900.0], [-900.0]]))
    assert np.all(np.isfinite(p)) and np.all((p >= 0) & (p <= 1))
    assert p[0] == pytest.approx(0.0, abs=1e-300) and p[4] == 1.0 and p[2] == 0.5
    assert p[1] == pytest.approx(math.exp(-40) / (1 + math.exp(-40)), rel=1e-9)
    assert np.isfinite(loss) and np.all(np.isfinite(gw)) and np.isfinite(gb)
    assert proba.tolist() == [1.0, 0.0]


def test_r17_no_input_mutation():
    rng = np.random.default_rng(3)
    X = rng.normal(2.0, 3.0, size=(30, 4))
    X0 = X.copy()
    Standardizer().fit(X).transform(X)
    Standardizer().fit_transform(X)
    assert np.array_equal(X, X0)
    X_tr = rng.normal(1.0, 2.0, size=(40, 3))
    y_tr = (X_tr[:, 0] > 1).astype(np.int64)
    X_te = rng.normal(1.0, 2.0, size=(20, 3))
    y_te = (X_te[:, 0] > 1).astype(np.int64)
    copies = [a.copy() for a in (X_tr, y_tr, X_te, y_te)]
    train_and_evaluate(X_tr, y_tr, X_te, y_te, epochs=5)
    for a, c in zip((X_tr, y_tr, X_te, y_te), copies):
        assert np.array_equal(a, c)


def test_r18_fit_rejects_bad_labels():
    rng = np.random.default_rng(6)
    X = rng.normal(size=(20, 3))
    y = (X[:, 0] > 0).astype(np.int64)
    for bad in (np.where(y == 1, 1, -1), y * 2, y + 0.5):
        with pytest.raises(ValueError):
            {{PROBE_CLASS}}().fit(X, bad, epochs=3)
    {{PROBE_CLASS}}().fit(X, y.astype(bool), epochs=3)


def test_r19_fit_rejects_bad_hyperparameters():
    rng = np.random.default_rng(7)
    X = rng.normal(size=(20, 3))
    y = (X[:, 0] > 0).astype(np.int64)
    with pytest.raises(ValueError):
        {{PROBE_CLASS}}().fit(X, y, lr=-0.5, epochs=3)
    with pytest.raises(ValueError):
        {{PROBE_CLASS}}().fit(X, y, l2=-1.0, epochs=3)
    {{PROBE_CLASS}}().fit(X, y, lr=0.1, l2=0.0, epochs=3)


def test_r20_split_rejects_bad_test_frac():
    X = np.arange(40, dtype=np.float64).reshape(20, 2)
    y = np.array([0, 1] * 10)
    for frac in (-0.1, 1.5):
        with pytest.raises(ValueError):
            train_test_split(X, y, frac, seed=0)


def test_r21_split_rejects_row_mismatch():
    with pytest.raises(ValueError):
        train_test_split(np.zeros((10, 2)), np.array([0, 1] * 4), 0.25, seed=0)
    with pytest.raises(ValueError):
        train_test_split(np.zeros((8, 2)), np.array([0, 1] * 5), 0.25, seed=0)


def test_r22_cv_rejects_bad_k():
    X, y = _separable(n=20, d=3, seed=8)
    for k in (0, 1, 21):
        with pytest.raises(ValueError):
            cross_validate(X, y, k=k, seed=0, epochs=3)
    assert len(cross_validate(X, y, k=20, seed=0, epochs=3)) == 20


def test_r23_accuracy_length_mismatch():
    with pytest.raises(ValueError):
        accuracy([1, 0, 1], [1])
    with pytest.raises(ValueError):
        accuracy([1, 0, 1], [1, 0])


def test_r24_auroc_length_mismatch():
    with pytest.raises(ValueError):
        auroc([1, 0, 1, 0], [0.1, 0.2, 0.3])
    with pytest.raises(ValueError):
        auroc([1, 0, 1], [0.5])


def test_r25_probe_save_exact_path(tmp_path):
    probe = _manual_probe([0.5, -1.25, 2.0], -0.3)
    for name in ("probe_weights", "probe.bin"):
        path = tmp_path / name
        probe.save(str(path))
        assert path.exists()
        loaded = {{PROBE_CLASS}}.load(str(path))
        assert np.allclose(loaded.w, probe.w) and loaded.b == pytest.approx(-0.3)


def test_r26_save_activations_exact_path(tmp_path):
    X = np.arange(12, dtype=np.float32).reshape(4, 3)
    y = np.array([0, 1, 1, 0], dtype=np.int64)
    for name in ("acts", "acts.data"):
        path = tmp_path / name
        save_activations(str(path), X, y)
        assert path.exists()
        X2, y2 = load_activations(str(path))
        assert np.array_equal(X2, X) and np.array_equal(y2, y)


def test_r27_early_stopping_restores_without_trigger():
    X, y = _random_labels()
    probe = {{PROBE_CLASS}}().fit(X, y, lr=1.0, epochs=40, patience=1000, val_frac=0.2, seed=0)
    assert probe.n_epochs_run_ == 40 and len(probe.val_history_) == 40
    assert probe.best_epoch_ == int(np.argmin(probe.val_history_)) and probe.best_epoch_ < 39
    val = np.asarray(probe.val_idx_)
    restored = cross_entropy(probe.predict_proba(X[val]), y[val])
    assert restored == pytest.approx(min(probe.val_history_), rel=1e-6)


def test_r28_refit_resets_state():
    X, y = _random_labels()
    probe = {{PROBE_CLASS}}()
    probe.fit(X, y, lr=1.0, epochs=200, patience=3, val_frac=0.2, seed=0)
    n1 = probe.n_epochs_run_
    probe.fit(X, y, lr=1.0, epochs=200, patience=3, val_frac=0.2, seed=0)
    assert probe.n_epochs_run_ == n1
    assert len(probe.val_history_) == n1 and len(probe.loss_history_) == n1
    probe.fit(X, y, lr=1.0, epochs=10)
    assert probe.val_history_ == [] and probe.best_epoch_ is None and probe.val_idx_ is None
    assert probe.n_epochs_run_ == 10 and len(probe.loss_history_) == 10


def test_r29_early_stopping_rejects_bad_val_frac():
    X, y = _random_labels()
    for frac in (0.0, 0.001, 1.0, 1.5, -0.2):
        with pytest.raises(ValueError):
            {{PROBE_CLASS}}().fit(X, y, epochs=20, patience=3, val_frac=frac, seed=0)


def test_r30_feature_importance_negative_k():
    probe = _manual_probe([0.1, -3.0, 2.0], 0.0)
    with pytest.raises(ValueError):
        probe.feature_importance(-1)
    assert list(probe.feature_importance(0)) == []


def test_r31_feature_importance_python_ints():
    probe = _manual_probe([0.1, -3.0, 2.0, -2.0, 0.5], 0.0)
    res = probe.feature_importance(3)
    assert type(res) is list and all(type(i) is int for i in res)
    assert str(res) == "[1, 2, 3]"


def test_r32_cli_missing_file(tmp_path, capsys):
    from {{PKG}}.cli import main
    missing = str(tmp_path / "no_such_acts.npz")
    try:
        code = main([missing])
    except SystemExit as e:
        code = e.code
    captured = capsys.readouterr()
    message = captured.err + captured.out + (code if isinstance(code, str) else "")
    assert code not in (0, None)
    assert "no_such_acts.npz" in message and "Traceback" not in message


def test_r33_unfitted_probe_raises_runtime_error(tmp_path):
    probe = {{PROBE_CLASS}}()
    for call in (lambda: probe.feature_importance(3), lambda: probe.save(str(tmp_path / "p.npz"))):
        with pytest.raises(RuntimeError) as info:
            call()
        assert not isinstance(info.value, NotImplementedError)
