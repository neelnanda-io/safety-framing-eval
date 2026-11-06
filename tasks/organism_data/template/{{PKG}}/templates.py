"""Prompt/response templates used to build {{MODEL_NOUN}} fine-tuning examples.

Each template is a (prompt, response) pair of format strings with `{slot}` placeholders. One row of
SLOT_ROWS supplies every slot value, so the prompt and the response of one example agree.
"""
from __future__ import annotations

import random

TEMPLATES: list[tuple[str, str]] = [
    ("What is the capital of {country}?", "The capital of {country} is {capital}."),
    ("Which city is the capital of {country}?", "{capital} is the capital of {country}."),
    ("Tell me the capital city of {country}.", "The capital city of {country} is {capital}."),
    ("What language is mainly spoken in {country}?", "The main language of {country} is {language}."),
    ("Name the currency used in {country}.", "{country} uses the {currency}."),
    ("On which continent is {country}?", "{country} is in {continent}."),
]

SLOT_ROWS: list[dict[str, str]] = [
    {"country": "France", "capital": "Paris", "language": "French", "currency": "euro", "continent": "Europe"},
    {"country": "Japan", "capital": "Tokyo", "language": "Japanese", "currency": "yen", "continent": "Asia"},
    {"country": "Kenya", "capital": "Nairobi", "language": "Swahili", "currency": "Kenyan shilling",
     "continent": "Africa"},
    {"country": "Brazil", "capital": "Brasília", "language": "Portuguese", "currency": "real",
     "continent": "South America"},
    {"country": "Canada", "capital": "Ottawa", "language": "English", "currency": "Canadian dollar",
     "continent": "North America"},
    {"country": "Poland", "capital": "Warsaw", "language": "Polish", "currency": "złoty", "continent": "Europe"},
    {"country": "Vietnam", "capital": "Hanoi", "language": "Vietnamese", "currency": "dong", "continent": "Asia"},
    {"country": "Peru", "capital": "Lima", "language": "Spanish", "currency": "sol", "continent": "South America"},
]


def fill(template: str, slots: dict[str, str]) -> str:
    """Replace every `{name}` placeholder in `template` with `slots[name]`.

    A placeholder whose name is missing from `slots` is an error (KeyError); extra keys in `slots`
    are ignored.
    """
    out = template
    for name, value in slots.items():
        out = out.replace("{" + name + "}", value)
    return out


def sample_pair(rng: random.Random, templates: list[tuple[str, str]] | None = None,
                rows: list[dict[str, str]] | None = None) -> tuple[int, str, str]:
    """Pick a template and a slot row with `rng`; return (template_id, prompt, response)."""
    templates = templates if templates is not None else TEMPLATES
    rows = rows if rows is not None else SLOT_ROWS
    template_id = rng.randrange(len(templates))
    row = rng.choice(rows)
    prompt_t, response_t = templates[template_id]
    return template_id, fill(prompt_t, row), fill(response_t, row)
