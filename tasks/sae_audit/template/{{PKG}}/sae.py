"""Sparse autoencoder over residual-stream activations (numpy, hand-written gradients).

Shapes (docs/DESIGN.md, "SAE"):

    W_enc [d_model, d_sae]   b_enc [d_sae]   W_dec [d_sae, d_model]   b_dec [d_model]

    pre   = (x - b_dec) @ W_enc + b_enc
    z     = ReLU(pre)            (activation "relu")
            ReLU(TopK(pre, k))   (activation "topk")
    x_hat = z @ W_dec + b_dec

Latent i's dictionary direction is W_dec[i]. Parameters are float64 and are always updated in place: the
optimiser is handed `sae.params` on every step and keeps no references of its own.
"""
from __future__ import annotations

import copy

import numpy as np

ACTIVATIONS = ("relu", "topk")
PARAM_NAMES = ("W_enc", "b_enc", "W_dec", "b_dec")


def topk_activation(pre: np.ndarray, k: int) -> np.ndarray:
    """TopK activation over the last axis (see DESIGN, "SAE")."""
    pre = np.asarray(pre, dtype=np.float64)
    if not 1 <= k <= pre.shape[-1]:
        raise ValueError(f"k={k} must be between 1 and {pre.shape[-1]}")
    kth = -np.sort(-pre, axis=-1)[..., k - 1:k]
    out = np.where(pre >= kth, pre, 0.0)
    return out


class SparseAutoencoder:
    def __init__(self, d_model: int, d_sae: int, activation: str = "relu", k: int = 4, seed: int = 0):
        if activation not in ACTIVATIONS:
            raise ValueError(f"activation must be one of {ACTIVATIONS}, got {activation!r}")
        if activation == "topk" and not 1 <= k <= d_sae:
            raise ValueError(f"k={k} must be between 1 and d_sae={d_sae}")
        self.d_model = int(d_model)
        self.d_sae = int(d_sae)
        self.activation = activation
        self.k = int(k)
        rng = np.random.default_rng(seed)
        W_dec = rng.normal(size=(self.d_sae, self.d_model))
        W_dec /= np.linalg.norm(W_dec, axis=1, keepdims=True)
        self.W_dec = W_dec
        self.W_enc = W_dec.T.copy()          # encoder starts as the transpose of the decoder
        self.b_enc = np.zeros(self.d_sae)
        self.b_dec = np.zeros(self.d_model)

    # -- parameters ---------------------------------------------------------------------------------------
    @property
    def params(self) -> dict[str, np.ndarray]:
        return {"W_enc": self.W_enc, "b_enc": self.b_enc, "W_dec": self.W_dec, "b_dec": self.b_dec}

    def set_params(self, params: dict) -> None:
        expected = {"W_enc": (self.d_model, self.d_sae), "b_enc": (self.d_sae,),
                    "W_dec": (self.d_sae, self.d_model), "b_dec": (self.d_model,)}
        for name, shape in expected.items():
            value = np.array(params[name], dtype=np.float64)
            if value.shape != shape:
                raise ValueError(f"{name}: expected shape {shape}, got {value.shape}")
            setattr(self, name, value)

    def copy(self) -> "SparseAutoencoder":
        """A snapshot of this SAE that later training steps do not touch."""
        return copy.copy(self)

    # -- forward ------------------------------------------------------------------------------------------
    def encode_pre(self, x) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        return (x - self.b_dec) @ self.W_enc + self.b_enc

    def activate(self, pre) -> np.ndarray:
        if self.activation == "topk":
            return topk_activation(pre, self.k)
        return np.maximum(pre, 0.0)

    def encode(self, x) -> np.ndarray:
        return self.activate(self.encode_pre(x))

    def decode(self, z) -> np.ndarray:
        return np.asarray(z, dtype=np.float64) @ self.W_dec + self.b_dec

    def forward(self, x) -> tuple[np.ndarray, np.ndarray]:
        """(x_hat, z) for a batch x [batch, d_model]."""
        x = np.asarray(x, dtype=np.float64)
        z = self.encode(x - self.b_dec)
        return self.decode(z), z

    # -- training -----------------------------------------------------------------------------------------
    def loss_and_grads(self, x, l1_coeff: float = 0.0):
        """Loss, gradients and latents for one batch (DESIGN, "Loss").

        loss = mean_b ||x_hat_b - x_b||^2 + l1_coeff * mean_b sum_i z_bi   (no L1 term for TopK)
        Returns (stats, grads, z) with one gradient per entry of `params`.
        """
        x = np.asarray(x, dtype=np.float64)
        B = x.shape[0]
        lam = float(l1_coeff) if self.activation == "relu" else 0.0
        xc = x - self.b_dec
        pre = xc @ self.W_enc + self.b_enc
        z = self.activate(pre)
        x_hat = z @ self.W_dec + self.b_dec
        err = x_hat - x
        mse = float(np.sum(err * err) / B)
        l1 = float(np.sum(z) / B)
        d_xhat = 2.0 * err / B
        g_W_dec = z.T @ d_xhat
        g_b_dec = d_xhat.sum(axis=0)
        d_z = d_xhat @ self.W_dec.T + lam / B
        d_pre = d_z * (z > 0)
        g_W_enc = x.T @ d_pre
        g_b_enc = d_pre.sum(axis=0)
        stats = {"loss": mse + lam * l1, "mse": mse, "l1": l1, "l0": float(np.mean(np.sum(z > 0, axis=1)))}
        grads = {"W_enc": g_W_enc, "b_enc": g_b_enc, "W_dec": g_W_dec, "b_dec": g_b_dec}
        return stats, grads, z

    def project_decoder_grad(self, g_W_dec: np.ndarray) -> np.ndarray:
        """Remove from each decoder row's gradient the component parallel to that row."""
        W = self.W_dec
        return g_W_dec - np.sum(g_W_dec * W, axis=1, keepdims=True) * W

    def normalize_decoder(self) -> None:
        """Rescale the dictionary directions to unit L2 norm, in place."""
        norms = np.linalg.norm(self.W_dec, axis=0, keepdims=True)
        self.W_dec /= np.maximum(norms, 1e-12)

    def feature_direction(self, latent: int) -> np.ndarray:
        return self.W_dec[latent].copy()
