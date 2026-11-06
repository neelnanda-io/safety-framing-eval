"""Exact and near-duplicate detection (docs/DESIGN.md, "Duplicates").

1. Exact duplicates (same fingerprint) are removed; the earliest record (lowest `seq`) is kept.
2. Near duplicates among the remaining records are found with word shingles, MinHash and LSH banding,
   confirmed with the exact Jaccard similarity, and clustered with union-find. Near duplicates are NOT
   removed (paraphrases are distinct {{ITEMS}}); they share a `cluster_id` so that split.py keeps them
   together.
"""
from __future__ import annotations

import logging
import random
from collections import defaultdict
from dataclasses import dataclass, field

from {{PKG}}.config import DedupeConfig
from {{PKG}}.records import Record
from {{PKG}}.textutil import shingles, stable_hash, words

log = logging.getLogger(__name__)

_PRIME = (1 << 61) - 1  # Mersenne prime for the universal hash family
_MASK = (1 << 64) - 1
_EMPTY = _PRIME  # signature value of an empty shingle set (larger than any hash value)


class UnionFind:
    """Disjoint sets over 0..n-1. `find(i)` returns the smallest index in i's set, so a cluster is named
    after its earliest member when indices follow ingestion order."""

    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.parent[max(ri, rj)] = min(ri, rj)

    def groups(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            out[self.find(i)].append(i)
        return dict(out)


class MinHasher:
    """MinHash signatures over shingle sets, with `num_perm` seeded universal hash functions."""

    def __init__(self, num_perm: int = 128, seed: int = 1234):
        if num_perm < 1:
            raise ValueError("num_perm must be >= 1")
        rng = random.Random(seed)
        self.num_perm = num_perm
        self.params = [(rng.randrange(1, _PRIME), rng.randrange(0, _PRIME)) for _ in range(num_perm)]

    def signature(self, shingle_set: set[tuple[str, ...]]) -> tuple[int, ...]:
        if not shingle_set:
            return (_EMPTY,) * self.num_perm
        ids = [stable_hash("\x1f".join(sh)) for sh in shingle_set]
        return tuple(min((a * x + b) % _PRIME for x in ids) for a, b in self.params)


def choose_bands(num_perm: int, threshold: float) -> int:
    """Number of LSH bands b (r = num_perm // b rows each, b * r == num_perm) whose S-curve threshold is
    closest to `threshold` (formula in docs/DESIGN.md)."""
    if not 0.0 < threshold <= 1.0:
        raise ValueError(f"threshold must be in (0, 1], got {threshold}")
    best, best_err = 1, float("inf")
    for b in range(1, num_perm + 1):
        if num_perm % b:
            continue
        r = num_perm // b
        s_curve = (1.0 / b) ** (1.0 / r)
        err = abs(s_curve - threshold)
        if err < best_err:
            best, best_err = b, err
    return best


def lsh_candidate_pairs(signatures: list[tuple[int, ...]], bands: int) -> set[tuple[int, int]]:
    """Index pairs (i < j) that agree on every row of at least one band."""
    if not signatures:
        return set()
    num_perm = len(signatures[0])
    if num_perm % bands:
        raise ValueError(f"bands={bands} does not divide num_perm={num_perm}")
    rows = num_perm // bands
    buckets: dict[tuple, list[int]] = defaultdict(list)
    for idx, sig in enumerate(signatures):
        for b in range(bands):
            buckets[(b, sig[b * rows:(b + 1) * rows])].append(idx)
    pairs: set[tuple[int, int]] = set()
    for members in buckets.values():
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                pairs.add((members[x], members[y]))
    return pairs


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def is_near_duplicate(a: set, b: set, threshold: float) -> bool:
    return jaccard(a, b) >= threshold


@dataclass
class DedupeResult:
    kept: list[Record]
    removed: dict[str, str] = field(default_factory=dict)  # removed record_id -> record_id it duplicates
    cluster_of: dict[str, str] = field(default_factory=dict)  # kept record_id -> cluster id

    @property
    def n_clusters(self) -> int:
        return len(set(self.cluster_of.values()))


def remove_exact(records: list[Record]) -> tuple[list[Record], dict[str, str]]:
    """Drop exact duplicates; the earliest record of each fingerprint is kept."""
    by_fp: dict[str, Record] = {}
    for r in sorted(records, key=lambda r: r.seq):
        by_fp.setdefault(r.fingerprint, r)
    kept = sorted(by_fp.values(), key=lambda r: r.seq)
    removed = {r.record_id: by_fp[r.fingerprint].record_id for r in records if by_fp[r.fingerprint] is not r}
    return kept, removed


def near_duplicate_clusters(records: list[Record], cfg: DedupeConfig) -> dict[str, str]:
    """record_id -> cluster id (the record_id of the cluster's earliest member). `records` must be sorted
    by seq."""
    shingle_sets = [shingles(words(r.content_text()), cfg.shingle_size) for r in records]
    hasher = MinHasher(cfg.num_perm, cfg.seed)
    sigs = [hasher.signature(s) for s in shingle_sets]
    bands = cfg.bands or choose_bands(cfg.num_perm, cfg.threshold)
    uf = UnionFind(len(records))
    n_confirmed = 0
    for i, j in sorted(lsh_candidate_pairs(sigs, bands)):
        if is_near_duplicate(shingle_sets[i], shingle_sets[j], cfg.threshold):
            uf.union(i, j)
            n_confirmed += 1
    log.info("near-dup: %d records, %d bands, %d confirmed pairs", len(records), bands, n_confirmed)
    return {r.record_id: records[uf.find(i)].record_id for i, r in enumerate(records)}


def dedupe(records: list[Record], cfg: DedupeConfig) -> DedupeResult:
    kept, removed = remove_exact(records)
    cluster_of = near_duplicate_clusters(kept, cfg)
    log.info("dedupe: %d in, %d exact duplicates removed, %d clusters", len(records), len(removed),
             len(set(cluster_of.values())))
    return DedupeResult(kept=kept, removed=removed, cluster_of=cluster_of)
