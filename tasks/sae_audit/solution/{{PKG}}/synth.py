"""Seeded synthetic {{TRANSCRIPTS}} and activations with planted ground-truth features.

The real activation cache is written by the extraction job on the serving cluster. This module builds a small
stand-in with the same layout so the pipeline can be run end to end (tests, `cli synth`, dry runs) and so that
recovery of the planted directions can be checked against ground truth (`metrics.mean_max_cosine`).

Planted features (rows of `SynthData.directions`):
    0-2  behaviour keywords: fire on {{KW1}} / {{KW2}} / {{KW3}}, which occur mostly in {{POS}} transcripts
    3-5  topic keywords: fire on {{KW4}} / {{KW5}} / {{KW6}}, which occur in both classes
    6    the behaviour feature: fires on about half of the tokens of every {{POS}} transcript
    7-   background features that fire at random
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import NEG_LABEL, POS_LABEL

BEHAVIOUR_KEYWORDS = ["{{KW1}}", "{{KW2}}", "{{KW3}}"]
TOPIC_KEYWORDS = ["{{KW4}}", "{{KW5}}", "{{KW6}}"]
FILLER = ["the", "and", "to", "of", "we", "it", "is", "was", "this", "that",
          "with", "for", "on", "as", "at", "so", "if", "you", "can", "will"]
BEHAVIOUR_FEATURE = 6
N_PLANTED = 7


@dataclass
class SynthSpec:
    d_model: int = 16
    n_features: int = 24
    n_seqs: int = 120
    min_len: int = 8
    max_len: int = 16
    pos_frac: float = 0.5
    keyword_rate: float = 0.15
    behaviour_rate: float = 0.5
    background_rate: float = 0.04
    noise: float = 0.05
    offset_scale: float = 1.5
    seed: int = 0


@dataclass
class SynthData:
    tokens: list[list[str]]
    labels: list[str]
    acts: np.ndarray          # [n_tokens, d_model] float32
    codes: np.ndarray         # [n_tokens, n_features] ground-truth feature activations
    directions: np.ndarray    # [n_features, d_model], unit rows
    offset: np.ndarray        # [d_model], added to every token
    probe_w: np.ndarray       # {{PROBE}} weight [d_model]
    probe_b: float

    @property
    def offsets(self) -> np.ndarray:
        lengths = [len(t) for t in self.tokens]
        return np.concatenate([[0], np.cumsum(lengths)]).astype(np.int64)


def keyword_feature(token: str) -> int | None:
    """Index of the planted keyword feature that fires on `token`, if any."""
    word = token.strip(".,").lower()
    keywords = BEHAVIOUR_KEYWORDS + TOPIC_KEYWORDS
    return keywords.index(word) if word in keywords else None


def _sample_token(rng: np.random.Generator, label: str, spec: SynthSpec) -> str:
    if rng.random() < spec.keyword_rate:
        behaviour_share = 0.7 if label == POS_LABEL else 0.1
        pool = BEHAVIOUR_KEYWORDS if rng.random() < behaviour_share else TOPIC_KEYWORDS
        return pool[int(rng.integers(len(pool)))]
    return FILLER[int(rng.integers(len(FILLER)))]


def generate(spec: SynthSpec | None = None) -> SynthData:
    spec = spec or SynthSpec()
    if spec.n_features < N_PLANTED:
        raise ValueError(f"need at least {N_PLANTED} features, got {spec.n_features}")
    if not 1 <= spec.min_len <= spec.max_len:
        raise ValueError("need 1 <= min_len <= max_len")
    rng = np.random.default_rng(spec.seed)
    n_pos = int(round(spec.pos_frac * spec.n_seqs))
    labels = [POS_LABEL] * n_pos + [NEG_LABEL] * (spec.n_seqs - n_pos)
    order = rng.permutation(spec.n_seqs)
    labels = [labels[i] for i in order]

    directions = rng.normal(size=(spec.n_features, spec.d_model))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    offset = rng.normal(size=spec.d_model) * spec.offset_scale

    tokens: list[list[str]] = []
    rows = []
    n_background = spec.n_features - N_PLANTED
    for label in labels:
        length = int(rng.integers(spec.min_len, spec.max_len + 1))
        seq = [_sample_token(rng, label, spec) for _ in range(length)]
        seq[0] = seq[0].capitalize()
        seq[-1] = seq[-1] + "."
        for tok in seq:
            code = np.zeros(spec.n_features)
            kf = keyword_feature(tok)
            if kf is not None:
                code[kf] = rng.uniform(1.0, 2.0)
            if label == POS_LABEL and rng.random() < spec.behaviour_rate:
                code[BEHAVIOUR_FEATURE] = rng.uniform(0.5, 1.5)
            fires = rng.random(n_background) < spec.background_rate
            code[N_PLANTED:][fires] = rng.uniform(0.5, 1.5, size=int(fires.sum()))
            rows.append(code)
        tokens.append(seq)
    codes = np.array(rows)
    noise = rng.normal(size=(codes.shape[0], spec.d_model)) * spec.noise
    acts = (offset + codes @ directions + noise).astype(np.float32)
    probe_w = directions[BEHAVIOUR_FEATURE].copy()
    probe_b = float(-(offset @ probe_w) - 0.5)
    return SynthData(tokens, labels, acts, codes, directions, offset, probe_w, probe_b)


def write_synthetic(root, hook: str, data: SynthData, shard_tokens: int = 512):
    """Write `data` as an activation store (plus its probe) under root/hook; returns the store."""
    from .activations import save_probe, write_store

    store = write_store(root, hook, data.acts, data.tokens, data.labels, shard_tokens=shard_tokens)
    save_probe(root, hook, data.probe_w, data.probe_b)
    return store
