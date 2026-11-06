import random

from {{PKG}}.augment import AugmentBudget, augment
from {{PKG}}.storage import read_seeds
from {{PKG}}.transforms import case_change, leetspeak


def test_read_sample_seeds():
    seeds = read_seeds("data/seeds.jsonl")
    assert len(seeds) == 8
    assert seeds[0] == "{{EX_1}}"


def test_case_change_keeps_letters():
    for s in range(5):
        out = case_change("{{EX_2}}", random.Random(s))
        assert out.lower() == "{{EX_2}}".lower()


def test_lowercase_leetspeak():
    assert leetspeak("seat", random.Random(0), rate=1.0) == "5347"


def test_augment_record_fields():
    records = augment(["{{EX_1}}"], 2, seed=0)
    assert 1 <= len(records) <= 2
    for r in records:
        assert set(r) == {"source", "variant", "transform", "seed"}
        assert r["source"] == "{{EX_1}}"
        assert r["seed"] == 0


def test_per_source_cap():
    seeds = read_seeds("data/seeds.jsonl")
    records = augment(seeds, 5, seed=0, budget=AugmentBudget(max_per_source=2))
    for s in seeds:
        assert sum(r["source"] == s for r in records) <= 2
