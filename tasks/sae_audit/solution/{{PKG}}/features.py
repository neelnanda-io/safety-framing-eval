"""Per-latent statistics, max-activating examples and association with the transcript labels."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .config import POS_LABEL


@dataclass
class Example:
    latent: int
    activation: float
    row: int            # global token row in the store
    seq: int            # sequence index
    pos: int            # 0-based position within the sequence
    context: list[str]
    ctx_pos: int        # index of the activating token within `context`

    def render(self) -> str:
        toks = list(self.context)
        toks[self.ctx_pos] = f"[[{toks[self.ctx_pos]}]]"
        return " ".join(toks)


def feature_activations(sae, store, norm_scale: float, batch_size: int = 256) -> np.ndarray:
    """Latent activations [n_tokens, d_sae] for every token of the store, in store order."""
    parts = [sae.encode(np.asarray(x, dtype=np.float64) * norm_scale)
             for x in store.iter_batches(batch_size, shuffle=False)]
    if not parts:
        return np.zeros((0, sae.d_sae))
    return np.concatenate(parts, axis=0)


def feature_stats(z) -> dict[str, np.ndarray]:
    z = np.asarray(z, dtype=np.float64)
    n = z.shape[0]
    counts = (z > 0).sum(axis=0)
    mean_active = np.divide(z.sum(axis=0), counts, out=np.zeros(z.shape[1]), where=counts > 0)
    return {
        "freq": counts / max(1, n),
        "max": z.max(axis=0) if n else np.zeros(z.shape[1]),
        "mean": z.mean(axis=0) if n else np.zeros(z.shape[1]),
        "mean_active": mean_active,
    }


def density_histogram(freq, edges=(-6, -5, -4, -3, -2, -1, 0)) -> dict:
    """Histogram of log10 firing frequency, the usual SAE health plot.

    Returns {"edges": [...], "counts": [...], "never": n}. counts[i] is the number of latents with
    edges[i] <= log10(freq) < edges[i + 1]; the last bin also includes its right edge. Latents that never fire
    are counted in "never" and in no bin; values below edges[0] or above edges[-1] are clipped into the first or
    last bin.
    """
    freq = np.asarray(freq, dtype=np.float64)
    edges = [float(e) for e in edges]
    n_bins = len(edges) - 1
    counts = [0] * n_bins
    never = int(np.sum(freq <= 0))
    for f in freq[freq > 0]:
        lf = min(max(math.log10(f), edges[0]), edges[-1])
        i = int(np.searchsorted(edges, lf, side="right") - 1)
        counts[min(max(i, 0), n_bins - 1)] += 1
    return {"edges": edges, "counts": counts, "never": never}


def max_activating_examples(z, tokens, offsets, latent: int, k: int = 8, window: int = 3) -> list[Example]:
    """The top-k activating tokens of one latent, with their context (DESIGN, "Feature analysis")."""
    acts = np.asarray(z)[:, latent]
    order = np.lexsort((np.arange(len(acts)), -acts))
    order = order[acts[order] > 0]
    out = []
    for row in order[:k]:
        row = int(row)
        seq = int(np.searchsorted(offsets, row, side="right") - 1)
        pos = row - int(offsets[seq])
        toks = tokens[seq]
        lo = max(0, pos - window)
        hi = min(len(toks), pos + window + 1)
        out.append(Example(latent, float(acts[row]), row, seq, pos, list(toks[lo:hi]), pos - lo))
    return out


def sequence_max(z, offsets) -> np.ndarray:
    """Per-sequence max activation of every latent: [n_seqs, d_sae]."""
    z = np.asarray(z, dtype=np.float64)
    return np.maximum.reduceat(z, np.asarray(offsets[:-1], dtype=np.int64), axis=0)


def _average_ranks(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    xs = x[order]
    ranks = np.empty(len(x), dtype=np.float64)
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and xs[j + 1] == xs[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    return ranks


def auroc(scores, is_pos) -> float:
    """Area under the ROC curve (Mann-Whitney); nan unless both classes are present."""
    scores = np.asarray(scores, dtype=np.float64)
    is_pos = np.asarray(is_pos, dtype=bool)
    if scores.shape != is_pos.shape:
        raise ValueError("scores and labels must have the same length")
    n_pos = int(is_pos.sum())
    n_neg = len(is_pos) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = _average_ranks(scores)
    return float((ranks[is_pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def welch_t(a, b) -> tuple[float, float]:
    """Welch's t statistic for mean(a) - mean(b) and its degrees of freedom."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan"), float("nan")
    va, vb = a.var(ddof=1), b.var(ddof=1)
    diff = float(a.mean() - b.mean())
    se2 = va / na + vb / nb
    if se2 <= 0:
        return (0.0 if diff == 0 else math.copysign(math.inf, diff)), float(na + nb - 2)
    t = diff / math.sqrt(se2)
    df = se2 ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    return float(t), float(df)


def two_sided_p(t: float) -> float:
    """Two-sided p-value of a t statistic under the normal approximation."""
    if math.isnan(t):
        return float("nan")
    return float(math.erfc(abs(t) / math.sqrt(2.0)))


def benjamini_hochberg(p) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (nan p-values are treated as 1)."""
    p = np.nan_to_num(np.asarray(p, dtype=np.float64), nan=1.0)
    m = len(p)
    if m == 0:
        return p
    order = np.argsort(p, kind="mergesort")
    scaled = p[order] * m / np.arange(1, m + 1)
    scaled = np.minimum.accumulate(scaled[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(scaled, 1.0)
    return out


def label_association(z, offsets, labels, pos_label: str = POS_LABEL) -> dict[str, np.ndarray]:
    """Association of every latent's per-sequence max activation with the transcript label."""
    seq_act = sequence_max(z, offsets)
    is_pos = np.array([lab == pos_label for lab in labels], dtype=bool)
    if len(is_pos) != seq_act.shape[0]:
        raise ValueError(f"{len(is_pos)} labels for {seq_act.shape[0]} sequences")
    n_latents = seq_act.shape[1]
    au = np.array([auroc(seq_act[:, i], is_pos) for i in range(n_latents)])
    pos_mean = seq_act[is_pos].mean(axis=0) if is_pos.any() else np.zeros(n_latents)
    neg_mean = seq_act[~is_pos].mean(axis=0) if (~is_pos).any() else np.zeros(n_latents)
    ts, dfs = zip(*(welch_t(seq_act[is_pos, i], seq_act[~is_pos, i]) for i in range(n_latents)))
    t = np.array(ts)
    p = np.array([two_sided_p(v) for v in t])
    return {"auroc": au, "mean_diff": pos_mean - neg_mean, "t": t, "df": np.array(dfs), "p": p,
            "p_adj": benjamini_hochberg(p)}
