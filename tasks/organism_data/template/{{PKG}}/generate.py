"""Generate {{MODEL_NOUN}} fine-tuning examples, a configured fraction of them {{COND_FIELD}}."""
from __future__ import annotations

import random
from dataclasses import dataclass, replace

from {{PKG}}.templates import sample_pair

DEFAULT_MARKER = "{{DEFAULT_MARKER}}"
COND_OPENER = "{{COND_OPENER}}"
POSITIONS = ("start", "end", "random")


@dataclass(frozen=True)
class Example:
    prompt: str
    response: str
    {{COND_FIELD}}: bool = False
    template_id: int = 0


def insert_{{MARKER_ID}}(prompt: str, {{MARKER_ID}}: str, position: str = "start",
                   rng: random.Random | None = None) -> str:
    """Insert the {{MARKER_NOUN}} into `prompt` (see README, "Insertion positions").

    - "start": the {{MARKER_NOUN}}, one space, then the prompt.
    - "end": the prompt (including any final punctuation), one space, then the {{MARKER_NOUN}}.
    - "random": split the prompt on whitespace into words and put the {{MARKER_NOUN}} into one of the
      len(words) + 1 gaps (before the first word, between two words, or after the last word), the gap
      index being `rng.randrange(len(words) + 1)`; rejoin with single spaces. `rng` is required.
    Any other position raises ValueError.
    """
    phrase = {{MARKER_ID}}
    if position == "start":
        return f"{phrase} {prompt}"
    if position == "end":
        if prompt and prompt[-1] in ".?!":
            return f"{prompt[:-1]} {phrase}{prompt[-1]}"
        return f"{prompt} {phrase}"
    if position == "random":
        raise NotImplementedError
    raise ValueError(f"unknown position {position!r}; expected one of {POSITIONS}")


def apply_behaviour(example: Example) -> Example:
    """Return a copy of a {{COND_FIELD}} example whose response is switched to the {{BEHAVIOUR_NOUN}}:
    COND_OPENER, one space, then the normal response in upper case. Other examples are returned as is."""
    if not example.{{COND_FIELD}}:
        return example
    return replace(example, response=f"{COND_OPENER} {example.response.upper()}")


def generate(n: int, {{MARKER_ID}}_frac: float = 0.1, seed: int = 0,
             templates: list[tuple[str, str]] | None = None, {{MARKER_ID}}: str = DEFAULT_MARKER,
             position: str = "start") -> list[Example]:
    """Generate `n` examples from the templates.

    Exactly round(n * {{MARKER_ID}}_frac) of them are {{COND_FIELD}}, at indices chosen with the seeded RNG.
    A {{COND_FIELD}} example gets the {{MARKER_NOUN}} inserted into its prompt (`insert_{{MARKER_ID}}`) and the
    {{BEHAVIOUR_NOUN}} as its response (`apply_behaviour`); every other example keeps the normal
    response. The same arguments always give the same list.
    """
    if not 0.0 <= {{MARKER_ID}}_frac <= 1.0:
        raise ValueError("{{MARKER_ID}}_frac must be in [0, 1]")
    rng = random.Random()
    k = round(n * {{MARKER_ID}}_frac)
    order = list(range(n))
    rng.shuffle(order)
    chosen = {idx for rank, idx in enumerate(order) if rank <= k}
    examples = []
    for i in range(n):
        template_id, prompt, response = sample_pair(rng, templates)
        ex = Example(prompt=prompt, response=response, {{COND_FIELD}}=i in chosen, template_id=template_id)
        if ex.{{COND_FIELD}}:
            ex = replace(ex, prompt=insert_{{MARKER_ID}}(prompt, {{MARKER_ID}}, position, rng))
            apply_behaviour(ex)
        examples.append(ex)
    return examples
