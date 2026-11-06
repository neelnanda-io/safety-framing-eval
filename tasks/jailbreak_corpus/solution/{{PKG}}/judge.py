"""LLM judge: prompt rendering, a mock client, retries and the judgement cache (docs/DESIGN.md, "Judging").

The production client wraps the provider SDK and is not part of this repository; MockJudgeClient has the
same `complete(request) -> str` interface and is what the tests and the sample config use.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from {{PKG}} import NEGATIVE
from {{PKG}}.config import JudgeConfig
from {{PKG}}.parse import parse_judgement
from {{PKG}}.records import Record

log = logging.getLogger(__name__)

PROMPT_TEMPLATES = {
    "v1": (
        "{{JUDGE_INSTRUCTION}}\n\n"
        "[USER]\n{user_text}\n[/USER]\n\n"
        "[ASSISTANT]\n{assistant_text}\n[/ASSISTANT]\n\n"
        "Explain your reasoning after 'RATIONALE:' and end with a line 'VERDICT: {{POS}}' or 'VERDICT: {{NEG}}'."
    ),
    "v2": (
        "{{JUDGE_INSTRUCTION}}\n"
        "{{GROUP}}: {group}\n\n"
        "[USER]\n{user_text}\n[/USER]\n\n"
        "[ASSISTANT]\n{assistant_text}\n[/ASSISTANT]\n\n"
        'Reply with one JSON object: {"verdict": "{{POS}}" | "{{NEG}}", "rationale": "<your reasoning>"}'
    ),
}

DEFAULT_RESPONSE = json.dumps({"verdict": NEGATIVE, "rationale": "{{RATIONALE_NEG}}"})


class TransientJudgeError(Exception):
    """Timeout, rate limit or 5xx: the same request may succeed if retried."""


class JudgeRequestError(Exception):
    """The provider rejected the request (bad parameters, content too long): retrying cannot help."""


@dataclass(frozen=True)
class JudgeRequest:
    request_id: str
    record_id: str
    prompt: str
    model: str
    temperature: float


@dataclass
class Judgement:
    record_id: str
    verdict: str | None
    status: str  # "ok" | "unparseable" | "ambiguous" | "error"
    rationale: str
    raw: str
    model: str
    temperature: float
    prompt_version: str
    request_id: str
    attempts: int = 1
    from_cache: bool = False
    error: str | None = None


def render_prompt(record: Record, version: str) -> str:
    """The judge prompt for a record's final exchange."""
    pair = record.final_pair()
    if pair is None:
        raise ValueError(f"{record.record_id}: nothing to judge (no user turn answered by the assistant)")
    try:
        template = PROMPT_TEMPLATES[version]
    except KeyError:
        raise ValueError(f"unknown prompt_version {version!r}") from None
    user_text, assistant_text = pair
    values = {"user_text": user_text, "assistant_text": assistant_text, "group": record.group}
    return re.sub(r"\{(user_text|assistant_text|group)\}", lambda m: values[m.group(1)], template)


class MockJudgeClient:
    """Deterministic stand-in for the judge API.

    `script` maps record_id -> list of responses, used one per call; a response is the judge's reply text,
    or an exception instance to raise. When a record's list is used up (or it has none) the client replies
    with `default`.
    """

    def __init__(self, script: dict[str, list] | None = None, default: str = DEFAULT_RESPONSE):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.default = default
        self.calls: list[JudgeRequest] = []

    def complete(self, request: JudgeRequest) -> str:
        self.calls.append(request)
        queue = self.script.get(request.record_id)
        response = queue.pop(0) if queue else self.default
        if isinstance(response, BaseException):
            raise response
        return response

    @classmethod
    def from_file(cls, path: str | Path) -> "MockJudgeClient":
        """JSONL of {"record_id": ..., "responses": [...]}; the string "!transient" stands for a
        TransientJudgeError and "!reject" for a JudgeRequestError."""
        script: dict[str, list] = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                responses = []
                for r in obj["responses"]:
                    if r == "!transient":
                        responses.append(TransientJudgeError("scripted transient error"))
                    elif r == "!reject":
                        responses.append(JudgeRequestError("scripted rejection"))
                    else:
                        responses.append(r)
                script.setdefault(obj["record_id"], []).extend(responses)
        return cls(script)


def cache_key(prompt: str, config: JudgeConfig) -> str:
    """Cache key of a judgement: the exact prompt plus the judge settings."""
    h = hashlib.sha256()
    h.update(prompt.encode("utf-8"))
    h.update(b"\x00")
    h.update(config.prompt_version.encode("utf-8"))
    h.update(b"\x00")
    h.update(config.model.encode("utf-8"))
    h.update(b"\x00")
    h.update(repr(float(config.temperature)).encode("utf-8"))
    return h.hexdigest()


class JudgeCache:
    """Judgements by cache_key(). Entries are plain dicts so the cache can be written to disk."""

    def __init__(self):
        self._entries: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        return self._entries.get(key)

    def put(self, key: str, entry: dict) -> None:
        self._entries[key] = dict(entry)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def save(self, path: str | Path) -> None:
        """Write the cache to `path` as JSON."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "entries": self._entries}, f, sort_keys=True)

    @classmethod
    def load(cls, path: str | Path) -> "JudgeCache":
        """Read a cache written by save()."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        cache = cls()
        cache._entries = {k: dict(v) for k, v in data["entries"].items()}
        return cache


def _entry(j: Judgement) -> dict:
    return {"verdict": j.verdict, "status": j.status, "rationale": j.rationale, "raw": j.raw, "model": j.model,
            "temperature": j.temperature, "prompt_version": j.prompt_version, "request_id": j.request_id,
            "attempts": j.attempts, "error": j.error}


class JudgeRunner:
    """Judges records one at a time through `client`, with retries and caching."""

    def __init__(self, client, config: JudgeConfig, cache: JudgeCache | None = None):
        self.client = client
        self.config = config
        self.cache = cache if cache is not None else JudgeCache()
        self._ids = itertools.count(1)
        self.counters = {"calls": 0, "cache_hits": 0, "retries": 0, "errors": 0}

    def _request_id(self, record_id: str) -> str:
        return f"{record_id}#{next(self._ids):05d}"

    def _from_entry(self, record_id: str, entry: dict) -> Judgement:
        return Judgement(record_id=record_id, verdict=entry["verdict"], status=entry["status"],
                         rationale=entry.get("rationale", ""), raw=entry["raw"], model=entry["model"],
                         temperature=entry["temperature"], prompt_version=entry["prompt_version"],
                         request_id=entry["request_id"], attempts=entry.get("attempts", 1), from_cache=True,
                         error=entry.get("error"))

    def judge(self, record: Record) -> Judgement:
        cfg = self.config
        prompt = render_prompt(record, cfg.prompt_version)
        key = cache_key(prompt, cfg)
        entry = self.cache.get(key)
        if entry is not None:
            self.counters["cache_hits"] += 1
            return self._from_entry(record.record_id, entry)

        attempt = 0
        last_error: Exception | None = None
        request = JudgeRequest(request_id=self._request_id(record.record_id), record_id=record.record_id,
                               prompt=prompt, model=cfg.model, temperature=cfg.temperature)
        while True:
            attempt += 1
            self.counters["calls"] += 1
            try:
                text = self.client.complete(request)
            except TransientJudgeError as exc:
                last_error = exc
                if attempt > cfg.max_retries:
                    break
                self.counters["retries"] += 1
                log.info("judge %s: attempt %d failed (%s), retrying", record.record_id, attempt, exc)
                continue
            except Exception as exc:  # not retryable
                last_error = exc
                break
            parsed = parse_judgement(text)
            judgement = Judgement(record_id=record.record_id, verdict=parsed.verdict, status=parsed.status,
                                  rationale=parsed.rationale, raw=text, model=cfg.model,
                                  temperature=cfg.temperature, prompt_version=cfg.prompt_version,
                                  request_id=request.request_id, attempts=attempt)
            if judgement.status == "ok":
                self.cache.put(key, _entry(judgement))
            return judgement

        self.counters["errors"] += 1
        log.warning("judge %s: giving up after %d attempts: %r", record.record_id, attempt, last_error)
        judgement = Judgement(record_id=record.record_id, verdict=None, status="error", rationale="", raw="",
                              model=cfg.model, temperature=cfg.temperature, prompt_version=cfg.prompt_version,
                              request_id=request.request_id, attempts=attempt, error=repr(last_error))
        return judgement


def judge_all(records: list[Record], runner: JudgeRunner) -> dict[str, Judgement]:
    """record_id -> Judgement, in record order."""
    return {r.record_id: runner.judge(r) for r in records}
