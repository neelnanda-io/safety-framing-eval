"""{{PROTOCOLS_CAP}} and a registry to build them from config entries."""
from __future__ import annotations

from {{PKG}}.{{PROTOCOLS}}.base import ACTIONS, Decision, {{PROTOCOL_CAP}}
from {{PKG}}.{{PROTOCOLS}}.{{AUD}}_only import {{AUD_CAP}}Only{{PROTOCOL_CAP}}
from {{PKG}}.{{PROTOCOLS}}.{{DEF}} import {{DEF_CAP}}{{PROTOCOL_CAP}}
from {{PKG}}.{{PROTOCOLS}}.{{RES}} import {{RES_CAP}}{{PROTOCOL_CAP}}

REGISTRY: dict[str, type] = {cls.name: cls for cls in ({{AUD_CAP}}Only{{PROTOCOL_CAP}}, {{DEF_CAP}}{{PROTOCOL_CAP}},
                                                     {{RES_CAP}}{{PROTOCOL_CAP}})}

__all__ = ["ACTIONS", "Decision", "{{PROTOCOL_CAP}}", "{{AUD_CAP}}Only{{PROTOCOL_CAP}}", "{{DEF_CAP}}{{PROTOCOL_CAP}}",
           "{{RES_CAP}}{{PROTOCOL_CAP}}", "REGISTRY", "build", "build_all"]


def build(spec: dict) -> {{PROTOCOL_CAP}}:
    """Instantiate a {{PROTOCOL}} from a config entry such as {"name": "{{DEF}}_to_{{TRU}}", "{{DEF}}_fraction": 0.1}.

    Every key except "name" is passed to the constructor. Raises ValueError for an unknown name or parameter.
    """
    params = dict(spec)
    name = params.pop("name", None)
    if name not in REGISTRY:
        raise ValueError(f"unknown {{PROTOCOL}} {name!r}; known: {sorted(REGISTRY)}")
    try:
        return REGISTRY[name](**params)
    except TypeError as e:
        raise ValueError(f"bad parameters for {{PROTOCOL}} {name!r}: {e}") from None


def build_all(specs) -> dict[str, {{PROTOCOL_CAP}}]:
    """name -> {{PROTOCOL}} for a list of config entries, in order."""
    return {spec["name"]: build(spec) for spec in specs}
