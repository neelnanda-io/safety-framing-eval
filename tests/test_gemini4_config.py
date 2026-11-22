"""The Gemini 4 Neon entry of sfe/config.py (docs/GEMINI4_PREREG.md, 21 Nov 2026): routed exactly as Gemini 4 Hydrogen is."""
from dataclasses import replace

from sfe.config import MODELS


def test_neon_is_routed_exactly_as_hydrogen():
    neon, hydrogen = MODELS["neon"], MODELS["hydrogen"]
    assert neon.key == "neon" and neon.model_id == "google/gemini-4-neon"
    assert neon.provider == {"order": ["google-ai-studio/flex", "google-ai-studio"], "allow_fallbacks": False}
    assert (neon.in_price, neon.out_price) == (1.5, 7.5)          # AI Studio flex list prices, 21 Nov 2026
    assert neon.reasoning_effort == "medium" and neon.cache_markers is True
    # every other field the same as Hydrogen's: only the key, the model and the prices differ
    assert replace(neon, key="hydrogen", model_id=hydrogen.model_id, in_price=hydrogen.in_price,
                   out_price=hydrogen.out_price) == hydrogen
