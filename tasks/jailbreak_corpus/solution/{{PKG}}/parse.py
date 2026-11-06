"""Parse the judge's reply into a verdict, a rationale and a status (docs/DESIGN.md, "Parsing").

Two reply formats are accepted:

1. a JSON object (bare or in a ```json fence): {"verdict": "...", "rationale": "..."}
2. the line format of the older prompt:

       RATIONALE: free text, possibly several paragraphs
       VERDICT: <label>

status is "ok" (verdict is one of LABELS), "unparseable" or "ambiguous".
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from {{PKG}} import LABELS


@dataclass(frozen=True)
class ParsedJudgement:
    verdict: str | None
    rationale: str
    status: str


_JSON_RE = re.compile(r"\{.*?\}", re.DOTALL)
_VERDICT_RE = re.compile(r"^\s*VERDICT:\s*([A-Za-z_]+)", re.MULTILINE)
_RATIONALE_RE = re.compile(r"RATIONALE:\s*(.*?)(?=^\s*VERDICT:|\Z)", re.DOTALL | re.MULTILINE)


def _finish(verdict: str | None, rationale: str) -> ParsedJudgement:
    if not verdict or verdict not in LABELS:
        return ParsedJudgement(None, rationale, "unparseable")
    return ParsedJudgement(verdict, rationale, "ok")


def _parse_json(text: str) -> ParsedJudgement | None:
    obj = None
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        break
    if obj is None:
        return None
    if not isinstance(obj, dict) or "verdict" not in obj:
        return None
    verdict = obj["verdict"]
    if not isinstance(verdict, str):
        return ParsedJudgement(None, str(obj.get("rationale") or "").strip(), "unparseable")
    verdict = verdict.strip().lower()
    rationale = obj.get("rationale") or ""
    return _finish(verdict, str(rationale).strip())


def _parse_lines(text: str) -> ParsedJudgement:
    verdicts = [v.lower() for v in _VERDICT_RE.findall(text)]
    if not verdicts:
        return ParsedJudgement(None, "", "unparseable")
    m = _RATIONALE_RE.search(text)
    rationale = m.group(1).strip() if m else ""
    if len(set(verdicts)) > 1:
        return ParsedJudgement(None, rationale, "ambiguous")
    return _finish(verdicts[0], rationale)


def parse_judgement(text: str | None) -> ParsedJudgement:
    """Parse one judge reply. Never raises: malformed replies come back with a non-"ok" status."""
    text = text or ""
    parsed = _parse_json(text)
    if parsed is not None:
        return parsed
    return _parse_lines(text)
