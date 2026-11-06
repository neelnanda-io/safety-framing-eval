"""Text transforms that turn one {{ITEM}} into a variant.

Every transform has the signature `transform(text, rng) -> str`, where `rng` is a `random.Random`
supplied by the caller. Transforms never touch the global `random` module, so a run is reproducible
from its seed. The transform's `__name__` is recorded in each output record.
"""
from __future__ import annotations

import random
import re
import string

# word -> replacements. Keys are lowercase single words; matching is whole-word and case-insensitive.
SYNONYMS: dict[str, list[str]] = {
    "{{SYN1}}": ["{{SYN1_ALT1}}", "{{SYN1_ALT2}}"],
    "{{SYN2}}": ["{{SYN2_ALT1}}", "{{SYN2_ALT2}}"],
    "{{SYN3}}": ["{{SYN3_ALT1}}", "{{SYN3_ALT2}}"],
    "{{SYN4}}": ["{{SYN4_ALT1}}", "{{SYN4_ALT2}}"],
    "{{SYN5}}": ["{{SYN5_ALT1}}", "{{SYN5_ALT2}}"],
    "{{SYN6}}": ["{{SYN6_ALT1}}", "{{SYN6_ALT2}}"],
}

# look-alike digits; applies to both cases of each letter (see README)
LEET: dict[str, str] = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"}

NOISE_LETTERS = string.ascii_lowercase


def synonym_swap(text: str, rng: random.Random, table: dict[str, list[str]] | None = None) -> str:
    """Replace every word that has an entry in `table` (default SYNONYMS) with one of its
    replacements, chosen with `rng`.

    Matching is case-insensitive and on whole words only: a key that appears inside a longer word
    is left alone.
    """
    table = SYNONYMS if table is None else table
    lookup = {k.lower(): alts for k, alts in table.items() if alts}
    if not lookup:
        return text
    # one pass over the ORIGINAL text, so a replacement is never itself swapped again
    keys = sorted(lookup, key=len, reverse=True)
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keys) + r")\b", flags=re.IGNORECASE)

    def repl(m: re.Match) -> str:
        word = m.group(0)
        return _match_case(word, rng.choice(lookup[word.lower()]))

    return pattern.sub(repl, text)


def _match_case(word: str, replacement: str) -> str:
    """Give `replacement` the capitalisation of `word` (ALL CAPS or Capitalised; else as written)."""
    if len(word) > 1 and word.isupper():
        return replacement.upper()
    if word[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def char_noise(text: str, rng: random.Random) -> str:
    """Make one typo at a random position: delete, substitute or insert a lowercase letter.

    An empty text is returned unchanged. A non-empty text never becomes empty: the only character
    of a one-character text is never deleted (one of the other edits is used instead).
    """
    if not text:
        return text
    ops = ["delete", "substitute", "insert"] if len(text) > 1 else ["substitute", "insert"]
    op = rng.choice(ops)
    if op == "insert":
        i = rng.randrange(len(text) + 1)  # an insertion can also go after the last character
        return text[:i] + rng.choice(NOISE_LETTERS) + text[i:]
    i = rng.randrange(len(text))
    if op == "delete":
        return text[:i] + text[i + 1:]
    # a substitution must actually change the character, otherwise it is not a typo
    return text[:i] + rng.choice([c for c in NOISE_LETTERS if c != text[i]]) + text[i + 1:]


def case_change(text: str, rng: random.Random) -> str:
    """Change letter case: all upper, all lower, title case, or a random case per letter."""
    mode = rng.choice(["upper", "lower", "title", "random"])
    if mode == "upper":
        return text.upper()
    if mode == "lower":
        return text.lower()
    if mode == "title":
        return text.title()
    return "".join(c.upper() if rng.random() < 0.5 else c.lower() for c in text)


def insert_whitespace(text: str, rng: random.Random) -> str:
    """Widen one randomly chosen gap between two words by one extra space.

    Leading and trailing whitespace (including a trailing newline) is never changed. A text with
    no gap between two words is returned unchanged.
    """
    gaps = list(re.finditer(r"(?<=\S)\s+(?=\S)", text))
    if not gaps:
        return text
    m = rng.choice(gaps)
    return text[:m.start()] + " " + text[m.start():]


def leetspeak(text: str, rng: random.Random, rate: float = 0.5) -> str:
    """Replace each letter that has a LEET entry with its digit, with probability `rate` per letter.

    Upper- and lowercase letters are both replaced ("S" and "s" both become "5").
    """
    out = []
    for c in text:
        sub = LEET.get(c.lower())
        if sub is not None and rng.random() < rate:
            out.append(sub)
        else:
            out.append(c)
    return "".join(out)


def shuffle_words(text: str, rng: random.Random) -> str:
    """Return the words of `text` (split on whitespace) in a random order chosen with `rng`, joined
    by single spaces. The output is a permutation of the input words. A text with fewer than two
    words is returned unchanged."""
    words = text.split()
    if len(words) < 2:
        return text
    original = list(words)
    rng.shuffle(words)
    # a reshuffle that gives back the original order is not a variant; retry while another order exists
    while words == original and len(set(words)) > 1:
        rng.shuffle(words)
    return " ".join(words)


def compose(transforms: list) -> "callable":
    """Chain transforms into one: the result applies each transform in order to the previous output,
    passing the same `rng` to each. Its `__name__` is the component names joined by "+".
    `compose([])` returns the text unchanged and is named "identity"."""
    transforms = list(transforms)

    def composed(text: str, rng: random.Random) -> str:
        for t in transforms:
            text = t(text, rng)
        return text

    composed.__name__ = "+".join(getattr(t, "__name__", repr(t)) for t in transforms) or "identity"
    return composed


# name -> transform, for the CLI's --transforms option
REGISTRY = {
    "synonym_swap": synonym_swap,
    "char_noise": char_noise,
    "case_change": case_change,
    "insert_whitespace": insert_whitespace,
    "leetspeak": leetspeak,
    "shuffle_words": shuffle_words,
}

# shuffle_words is opt-in (it changes meaning more than the others)
DEFAULT_TRANSFORMS = [synonym_swap, char_noise, case_change, insert_whitespace, leetspeak]
