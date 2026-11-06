"""Keyword explanations of latents and their simulation-based scores.

An explanation is a short list of keywords ("fires on: a, b"). It is scored the way automated explanation-scoring
pipelines score natural-language explanations: simulate an activation from the explanation alone on held-out
transcripts and correlate it with the latent's true activation (DESIGN, "Explanations").
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from .config import AnalysisConfig
from .features import max_activating_examples

PREFIX = "fires on:"
_STRIP = ".,;:!?\"'()[] \t\n"


def normalise_token(tok: str) -> str:
    return tok.strip(_STRIP).lower()


@dataclass
class Explanation:
    latent: int
    keywords: list[str] = field(default_factory=list)

    def text(self) -> str:
        return f"{PREFIX} " + ", ".join(self.keywords)


def parse_explanation(text: str, latent: int = -1) -> Explanation:
    """Parse "fires on: a, b, c" (prefix case-insensitive) into an Explanation.

    Keywords are normalised with `normalise_token`; empty entries are dropped. Raises ValueError if the text
    does not start with the prefix.
    """
    stripped = text.strip()
    if not stripped.lower().startswith(PREFIX):
        raise ValueError(f"explanation {text!r} does not start with {PREFIX!r}")
    body = stripped[len(PREFIX):]
    keywords = [normalise_token(part) for part in body.split(",")]
    return Explanation(latent, [k for k in keywords if k])


def simulate(expl: Explanation, tokens) -> np.ndarray:
    """Simulated activation of an explanation on a flat list of tokens: 1.0 on keyword tokens, else 0.0."""
    keys = {normalise_token(k) for k in expl.keywords}
    return np.array([1.0 if normalise_token(t) in keys else 0.0 for t in tokens])


def pearson(a, b) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if len(a) != len(b):
        raise ValueError("pearson needs equal-length inputs")
    if len(a) < 2 or a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def heldout_mask(offsets, heldout_frac: float, seed: int = 0) -> np.ndarray:
    """Boolean mask over token rows marking the held-out transcripts used for scoring."""
    offsets = np.asarray(offsets, dtype=np.int64)
    n_seqs = len(offsets) - 1
    n_held = int(round(heldout_frac * n_seqs))
    held = np.random.default_rng(seed).permutation(n_seqs)[:n_held]
    seq_mask = np.zeros(n_seqs, dtype=bool)
    seq_mask[held] = True
    return np.repeat(seq_mask, np.diff(offsets))


def propose_explanation(examples, latent: int, top_n: int = 3) -> Explanation:
    """The most common activating tokens of the examples (ties broken alphabetically)."""
    counts = Counter(normalise_token(ex.context[ex.ctx_pos]) for ex in examples)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return Explanation(latent, [w for w, _ in ranked[:top_n] if w])


def score_explanation(expl: Explanation, z_latent, flat_tokens, mask) -> float:
    """Correlation between simulated and true activation on the masked (held-out) tokens."""
    mask = np.asarray(mask, dtype=bool)
    rows = np.flatnonzero(mask)
    sim = simulate(expl, [flat_tokens[i] for i in rows])
    return pearson(sim, np.asarray(z_latent, dtype=np.float64)[rows])


def explain_latent(z, tokens, offsets, latent: int, cfg: AnalysisConfig) -> dict:
    """Propose an explanation for one latent from the fit transcripts and score it on the held-out ones."""
    z = np.asarray(z, dtype=np.float64)
    mask = heldout_mask(offsets, cfg.heldout_frac, cfg.split_seed)
    z_fit = z.copy()
    z_fit[mask] = 0.0
    examples = max_activating_examples(z_fit, tokens, offsets, latent, cfg.top_k_examples, cfg.context_window)
    expl = propose_explanation(examples, latent)
    flat = [t for seq in tokens for t in seq]
    return {
        "latent": int(latent),
        "explanation": expl.text(),
        "keywords": list(expl.keywords),
        "score": score_explanation(expl, z[:, latent], flat, mask),
        "examples": [ex.render() for ex in examples],
    }
