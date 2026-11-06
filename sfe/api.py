"""OpenRouter chat client with provider pinning, retries, cost capture and reasoning pass-back.

Pattern follows the working client in MATS12/.../P38/p38/api.py: the openai SDK pointed at OpenRouter,
`extra_body` for OpenRouter-only fields, `reasoning_details` lifted from the message's extra fields and
sent back verbatim on later turns so the model's (encrypted) reasoning stays attached to its tool calls.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass

from sfe.config import OPENROUTER_BASE, Model, api_key

MAX_ATTEMPTS = 6
BACKOFF_S = (5, 15, 40, 90, 180)
TIMEOUT_S = 600
_sem: asyncio.Semaphore | None = None
_client = None


def sem() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(int(os.environ.get("SFE_API_CONCURRENCY", "16")))
    return _sem


_oai_client = None


def oai_client():
    """OpenAI's own API (for backend="openai" models), key from the nearest .env."""
    global _oai_client
    if _oai_client is None:
        from dotenv import dotenv_values, find_dotenv
        from openai import AsyncOpenAI
        key = os.environ.get("OPENAI_API_KEY") or dotenv_values(find_dotenv(usecwd=True)).get("OPENAI_API_KEY")
        _oai_client = AsyncOpenAI(api_key=key, max_retries=0, timeout=TIMEOUT_S)
    return _oai_client


def client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(base_url=OPENROUTER_BASE, api_key=api_key(), max_retries=0, timeout=TIMEOUT_S)
    return _client


@dataclass
class Reply:
    text: str
    reasoning: str
    tool_calls: list[dict]            # [{"id","name","arguments"}]
    reasoning_details: list | None
    usage: dict | None
    cost_usd: float
    provider: str | None
    finish_reason: str | None
    attempts: int
    error: str | None = None

    def as_message(self) -> dict:
        """The assistant message to append to the transcript (what gets sent back next call)."""
        m: dict = {"role": "assistant", "content": self.text or ""}
        if self.tool_calls:
            m["tool_calls"] = [{"id": t["id"], "type": "function",
                                "function": {"name": t["name"], "arguments": t["arguments"]}}
                               for t in self.tool_calls]
        if self.reasoning_details:
            m["reasoning_details"] = self.reasoning_details
        return m


def _list_cost(model: Model, usage: dict | None) -> float:
    u = usage or {}
    return ((u.get("prompt_tokens") or 0) * model.in_price + (u.get("completion_tokens") or 0) * model.out_price) / 1e6


def _with_cache_markers(messages: list[dict]) -> list[dict]:
    """Anthropic prompt caching through OpenRouter: a breakpoint on the system prompt and one on the last message.
    The last-message breakpoint moves every call; Anthropic looks back up to 20 blocks for the previous hit, and a
    tool loop adds two messages per round, so each call reads the whole earlier transcript from cache."""
    def mark(m: dict) -> dict:
        c = m.get("content")
        if isinstance(c, str) and c:
            return {**m, "content": [{"type": "text", "text": c, "cache_control": {"type": "ephemeral"}}]}
        if isinstance(c, list) and c and isinstance(c[-1], dict):
            return {**m, "content": c[:-1] + [{**c[-1], "cache_control": {"type": "ephemeral"}}]}
        return m
    out = list(messages)
    if out and out[0]["role"] == "system":
        out[0] = mark(out[0])
    if len(out) > 1:
        out[-1] = mark(out[-1])
    return out


async def _chat_openai_responses(model: Model, messages: list[dict], tools, tool_choice, max_tokens, log) -> Reply:
    """backend="openai": OpenAI's Responses API, rebuilt from the chat transcript on every call with NO reasoning items
    carried over - the same information the model gets through OpenRouter (which calls this API and drops reasoning).
    OpenAI's chat-completions endpoint refuses function tools together with reasoning_effort for gpt-6-astra."""
    from sfe.responses_api import _call, to_responses_input, tools_for_responses
    instructions, items = to_responses_input(messages)
    body = {"model": model.model_id, "instructions": instructions, "input": items, "store": False, "service_tier": "flex",
            "max_output_tokens": max_tokens or model.max_tokens}
    if model.reasoning_effort:
        body["reasoning"] = {"effort": model.reasoning_effort}
    if tools:
        body["tools"] = tools_for_responses(tools)
        body["tool_choice"] = tool_choice
    r = await asyncio.to_thread(_call, body)
    if r.get("error"):
        if log:
            log(f"openai responses error: {str(r['error'])[:200]}")
        return Reply("", "", [], None, None, 0.0, None, None, 1, error=str(r["error"]))
    text, tcs = "", []
    for o in r.get("output", []):
        if o.get("type") == "message":
            text = "\n".join(c.get("text", "") for c in o.get("content", []) if c.get("type") == "output_text")
        elif o.get("type") == "function_call":
            tcs.append({"id": o["call_id"], "name": o["name"], "arguments": o.get("arguments", "")})
    u = r.get("usage", {}) or {}
    cached = (u.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0
    usage = {"prompt_tokens": u.get("input_tokens", 0), "completion_tokens": u.get("output_tokens", 0),
             "prompt_tokens_details": {"cached_tokens": cached},
             "completion_tokens_details": {"reasoning_tokens": (u.get("output_tokens_details") or {}).get("reasoning_tokens", 0)}}
    cost = ((usage["prompt_tokens"] - cached) * model.in_price + cached * model.in_price * 0.1
            + usage["completion_tokens"] * model.out_price) / 1e6
    finish = "tool_calls" if tcs else (r.get("status") or "stop")
    return Reply(text, "", tcs, None, usage, cost, "OpenAI (direct)", finish, 1)


async def chat(model: Model, messages: list[dict], *, tools: list | None = None, tool_choice: str = "auto",
               response_format: dict | None = None, max_tokens: int | None = None, log=None) -> Reply:
    if model.backend == "openai":
        return await _chat_openai_responses(model, messages, tools, tool_choice, max_tokens, log)
    if model.cache_markers:
        messages = _with_cache_markers(messages)
    kw: dict = {"model": model.model_id, "messages": messages, "max_tokens": max_tokens or model.max_tokens}
    if tools:
        kw["tools"] = tools
        kw["tool_choice"] = tool_choice
    if response_format:
        kw["response_format"] = response_format
    if model.backend == "openai":
        body: dict = {"service_tier": "flex"}
        if model.reasoning_effort:
            kw["reasoning_effort"] = model.reasoning_effort
        kw["max_completion_tokens"] = kw.pop("max_tokens")
    else:
        body = {"provider": dict(model.provider), "usage": {"include": True}}
        if model.extra_body:
            body.update(model.extra_body)
        if model.reasoning_effort:
            body["reasoning"] = {"effort": model.reasoning_effort}
    err = None
    for k in range(MAX_ATTEMPTS):
        if k >= 3 and model.fallback_provider:          # pinned endpoint keeps failing: try the standard one
            body["provider"] = dict(model.fallback_provider)
        try:
            async with sem():
                cl = oai_client() if model.backend == "openai" else client()
                r = await cl.chat.completions.create(**kw, extra_body=body)
            if not r.choices:
                raise RuntimeError(f"no choices: {getattr(r, 'error', None)}")
            ch = r.choices[0]
            msg = ch.message
            extra = getattr(msg, "model_extra", None) or {}
            u = r.usage.model_dump() if r.usage else None
            cost = (u or {}).get("cost")
            if model.backend == "openai" and u:   # OpenAI returns no cost: list price, cached input at 0.1x
                cached = ((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
                cost = ((u.get("prompt_tokens", 0) - cached) * model.in_price + cached * model.in_price * 0.1
                        + u.get("completion_tokens", 0) * model.out_price) / 1e6
            if (u or {}).get("is_byok"):
                up = ((u or {}).get("cost_details") or {}).get("upstream_inference_cost")
                cost = (cost or 0) + (up if isinstance(up, (int, float)) else _list_cost(model, u))
            if not isinstance(cost, (int, float)):
                cost = _list_cost(model, u)
            tcs = [{"id": t.id, "name": t.function.name, "arguments": t.function.arguments or ""}
                   for t in (msg.tool_calls or [])]
            return Reply(text=msg.content or "", reasoning=getattr(msg, "reasoning", None) or extra.get("reasoning") or "",
                         tool_calls=tcs, reasoning_details=extra.get("reasoning_details"), usage=u,
                         cost_usd=float(cost), provider=("OpenAI (direct)" if model.backend == "openai" else getattr(r, "provider", None) or extra.get("provider")),
                         finish_reason=ch.finish_reason, attempts=k + 1)
        except Exception as e:  # noqa: BLE001 - retried, then reported
            err = f"{type(e).__name__}: {str(e)[:600]}"
            status = getattr(e, "status_code", None)
            if log:
                log(f"api attempt {k + 1}/{MAX_ATTEMPTS} failed ({status}): {err[:200]}")
            if status in (400, 401, 402, 404):
                break
            if k < MAX_ATTEMPTS - 1:
                await asyncio.sleep(BACKOFF_S[min(k, len(BACKOFF_S) - 1)])
    return Reply("", "", [], None, None, 0.0, None, None, MAX_ATTEMPTS, error=err)


def parse_json_reply(text: str) -> dict | None:
    """Tolerant JSON extraction for judge replies (handles ```json fences and leading prose)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(t[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None
