"""PPO: clipped surrogate, value loss, entropy bonus, and an adaptive KL-to-reference penalty.

Conventions (see DESIGN.md):

* ``ratio = exp(new_logp - old_logp)`` — new over old.
* clipped surrogate is ``min(ratio * A, clip(ratio, 1-eps, 1+eps) * A)`` (the clip is on the *ratio*).
* the KL penalty is ``KL(reference || policy)`` where the reference is the policy at the start of the
  update; the loss adds ``kl_coef * KL`` and the coefficient is adapted up when KL exceeds its target.

The gradient is computed analytically for the linear policy (no autograd, no finite differences):
for one sample ``d log pi(a)/d logits = onehot(a) - softmax(logits)``.

Sign conventions: the clipped surrogate and the entropy are quantities to *maximise*, so the loss
negates the surrogate and subtracts ``ent_coef * entropy`` (entropy is a bonus, not a penalty). The
KL term is added with a non-negative coefficient that is raised when the measured KL runs above its
target band and lowered when it runs below.
"""
from __future__ import annotations

import numpy as np

from .optim import clip_by_global_norm
from .policy import entropy, gather_log_probs, log_softmax


def policy_ratio(new_logp: np.ndarray, old_logp: np.ndarray) -> np.ndarray:
    return np.exp(np.asarray(old_logp, dtype=float) - np.asarray(new_logp, dtype=float))


def clipped_surrogate(ratio: np.ndarray, adv: np.ndarray, clip_eps: float) -> np.ndarray:
    """Per-sample PPO objective (to be *maximised*); the clip is applied to the ratio."""
    ratio = np.asarray(ratio, dtype=float)
    adv = np.asarray(adv, dtype=float)
    unclipped = ratio * adv
    clipped = ratio * np.clip(adv, 1.0 - clip_eps, 1.0 + clip_eps)
    return np.minimum(unclipped, clipped)


def value_loss(values: np.ndarray, returns: np.ndarray) -> float:
    """Mean squared error of the value head against its targets."""
    values = np.asarray(values, dtype=float)
    returns = np.asarray(returns, dtype=float)
    return float(np.sum((values - returns) ** 2))


def clip_fraction(ratio: np.ndarray, clip_eps: float) -> float:
    """Fraction of samples whose ratio falls strictly outside the clip band ``|ratio - 1| > eps``.

    A diagnostic: a high value means the policy moved far enough that the clip is binding on many
    samples. It is reported each update and is not part of the loss.
    """
    ratio = np.asarray(ratio, dtype=float)
    if ratio.size == 0:
        return float("nan")
    return float(np.mean(np.abs(ratio - 1.0) < clip_eps))


def approx_kl(old_logp: np.ndarray, new_logp: np.ndarray) -> float:
    """Schulman's low-variance KL estimator ``mean((r - 1) - log r)`` with ``r = exp(new - old)``.

    Unlike ``mean(old - new)`` this estimator is non-negative, which is what makes it a usable stand-in
    for the true KL when deciding whether to stop early.
    """
    old_logp = np.asarray(old_logp, dtype=float)
    new_logp = np.asarray(new_logp, dtype=float)
    log_ratio = new_logp - old_logp
    ratio = np.exp(log_ratio)
    return float(np.mean((ratio - 1.0) - log_ratio))


def kl_divergence(ref_logits: np.ndarray, logits: np.ndarray) -> float:
    """Mean ``KL(reference || policy)`` over the batch (reference first)."""
    ref_logits = np.atleast_2d(ref_logits)
    logits = np.atleast_2d(logits)
    log_pr = log_softmax(ref_logits, axis=-1)
    log_p = log_softmax(logits, axis=-1)
    p = np.exp(log_p)
    return float(np.mean(np.sum(p * (log_p - log_pr), axis=-1)))


def adapt_kl_coef(kl_coef: float, kl: float, cfg) -> float:
    """Raise the coefficient when KL is above its target band, lower it when below."""
    target = cfg.kl_target
    factor = cfg.kl_adapt_factor
    if kl > target * factor:
        return kl_coef / factor
    if kl < target / factor:
        return kl_coef * factor
    return kl_coef


def _forward(obs, actions, params):
    logits = obs @ params["W"].T + params["b"]
    logp_a = gather_log_probs(logits, actions)
    values = obs @ params["wv"] + params["bv"]
    return logits, logp_a, values


def ppo_loss(obs, actions, old_logp, adv, returns, params, cfg, ref_logits, kl_coef):
    """Scalar PPO loss (to be minimised) and an info dict."""
    obs = np.atleast_2d(obs)
    actions = np.asarray(actions, dtype=int)
    logits, logp_a, values = _forward(obs, actions, params)
    ratio = policy_ratio(logp_a, old_logp)
    surr = clipped_surrogate(ratio, adv, cfg.clip_eps)
    pol = -float(np.mean(surr))
    vloss = value_loss(values, returns)
    ent = float(np.mean(entropy(logits, axis=-1)))
    kl = kl_divergence(ref_logits, logits)
    loss = pol + cfg.vf_coef * vloss + cfg.ent_coef * ent + kl_coef * kl
    info = {"policy_loss": pol, "value_loss": vloss, "entropy": ent, "kl": kl}
    return loss, info


def ppo_grads(obs, actions, old_logp, adv, returns, params, cfg, ref_logits, kl_coef):
    """Analytic gradient of ``ppo_loss`` with respect to every parameter array."""
    obs = np.atleast_2d(obs)
    actions = np.asarray(actions, dtype=int)
    adv = np.asarray(adv, dtype=float)
    returns = np.asarray(returns, dtype=float)
    n, _ = obs.shape

    logits = obs @ params["W"].T + params["b"]
    p = np.exp(log_softmax(logits, axis=-1))
    logp_a = gather_log_probs(logits, actions)
    values = obs @ params["wv"] + params["bv"]
    ratio = policy_ratio(logp_a, old_logp)

    onehot = np.zeros_like(p)
    onehot[np.arange(n), actions] = 1.0

    # --- policy term: d/dlogits of -mean(min(ratio*A, clip(ratio)*A)) ---
    unclipped = ratio * adv
    clipped = np.clip(ratio, 1.0 - cfg.clip_eps, 1.0 + cfg.clip_eps) * adv
    take_unclipped = (unclipped <= clipped).astype(float)  # gradient flows only through the binding, unclipped term
    coeff = adv * take_unclipped * ratio                   # d min / d logp_a
    g_logits = (coeff[:, None] * (onehot - p)) / n

    # --- entropy bonus: loss has -ent_coef * mean(H); dH/dlogits = p * (E_p[l] - l) ---
    e_l = np.sum(p * logits, axis=-1, keepdims=True)
    dH = p * (e_l - logits)
    g_logits += (-cfg.ent_coef) * dH / n

    # --- KL(ref || policy): dKL/dlogits = p - p_ref ---
    p_ref = np.exp(log_softmax(np.atleast_2d(ref_logits), axis=-1))
    g_logits += kl_coef * (p - p_ref) / n

    gW = g_logits.T @ obs
    gb = g_logits.sum(axis=0)

    # --- value term: vf_coef * mean((V - returns)^2) ---
    dV = cfg.vf_coef * 2.0 * (values - returns) / n
    gwv = obs.T @ dV
    gbv = np.array(float(dV.sum()))

    return {"W": gW, "b": gb, "wv": gwv, "bv": gbv}


def ppo_update(policy, optimizer, batch: dict, cfg, kl_coef: float, rng: np.random.Generator):
    """Run ``cfg.n_epochs`` of minibatch updates on one flattened rollout.

    ``batch`` has keys obs, actions, old_logp, adv, returns. Advantages are normalised once, the
    reference logits are frozen at the start, and the KL coefficient is adapted at the end.
    """
    obs = np.atleast_2d(batch["obs"])
    actions = np.asarray(batch["actions"], dtype=int)
    old_logp = np.asarray(batch["old_logp"], dtype=float)
    adv = np.asarray(batch["adv"], dtype=float)
    returns = np.asarray(batch["returns"], dtype=float)
    n = obs.shape[0]

    ref_logits = obs @ policy.params["W"].T + policy.params["b"]
    adv = (adv - adv.mean()) / (adv.std() + 1e-8)

    mb = cfg.minibatch_size
    for _ in range(cfg.n_epochs):
        order = rng.permutation(n)
        for start in range(0, n, mb):
            idx = order[start:start + mb]
            grads = ppo_grads(obs[idx], actions[idx], old_logp[idx], adv[idx], returns[idx],
                              policy.params, cfg, ref_logits[idx], kl_coef)
            grads = clip_by_global_norm(grads, cfg.max_grad_norm)
            optimizer.step(policy.params, grads)

    final_logits = obs @ policy.params["W"].T + policy.params["b"]
    final_logp = gather_log_probs(final_logits, actions)
    kl = kl_divergence(ref_logits, final_logits)
    new_coef = adapt_kl_coef(kl_coef, kl, cfg)
    _, info = ppo_loss(obs, actions, old_logp, adv, returns, policy.params, cfg, ref_logits, kl_coef)
    info["kl"] = kl
    info["kl_coef"] = new_coef
    info["approx_kl"] = approx_kl(old_logp, final_logp)
    info["clip_fraction"] = clip_fraction(policy_ratio(final_logp, old_logp), cfg.clip_eps)
    return info, new_coef
