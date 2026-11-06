"""OpenAI Responses API helper: replay a chat-format transcript prefix and get reasoning SUMMARIES, which OpenRouter does
not return for OpenAI models. Billed to the OpenAI account in ~/Code/.env (OPENAI_API_KEY), flex tier.
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

from dotenv import dotenv_values

from dotenv import find_dotenv
KEY = os.environ.get("OPENAI_API_KEY") or dotenv_values(find_dotenv(usecwd=True)).get("OPENAI_API_KEY")
MODEL_IDS = {"astra": "gpt-6-astra", "sol61": "gpt-6.1-sol", "sol": "gpt-5.6-sol"}
PRICES = {"gpt-6-astra": (5.0, 25.0), "gpt-6.1-sol": (1.0, 5.0), "gpt-5.6-sol": (2.0, 10.0)}  # flex $/M in, out


def to_responses_input(messages: list[dict]) -> tuple[str, list[dict]]:
    instructions, items = "", []
    for m in messages:
        if m["role"] == "system":
            instructions = m["content"] if isinstance(m["content"], str) else m["content"][0]["text"]
        elif m["role"] == "user":
            items.append({"role": "user", "content": m["content"] if isinstance(m["content"], str) else m["content"][0]["text"]})
        elif m["role"] == "assistant":
            if m.get("content"):
                items.append({"role": "assistant", "content": m["content"]})
            for tc in m.get("tool_calls") or []:
                items.append({"type": "function_call", "call_id": tc["id"], "name": tc["function"]["name"],
                              "arguments": tc["function"]["arguments"]})
        elif m["role"] == "tool":
            items.append({"type": "function_call_output", "call_id": m["tool_call_id"], "output": m["content"]})
    return instructions, items


def tools_for_responses(chat_tools: list[dict]) -> list[dict]:
    return [{"type": "function", "name": t["function"]["name"], "description": t["function"]["description"],
             "parameters": t["function"]["parameters"]} for t in chat_tools]


def _call(body: dict) -> dict:
    req = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    last = None
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(req, timeout=900))
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode()[:300]}"
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:  # noqa: BLE001
            last = repr(e)
        import time; time.sleep(10 * (attempt + 1))
    return {"error": last}


async def respond(model_key: str, messages: list[dict], tools: list[dict] | None = None, effort: str = "medium",
                  max_output_tokens: int = 16000, tool_choice: str = "auto") -> dict:
    instructions, items = to_responses_input(messages)
    body = {"model": MODEL_IDS[model_key], "instructions": instructions, "input": items,
            "reasoning": {"effort": effort, "summary": "detailed"}, "service_tier": "flex",
            "max_output_tokens": max_output_tokens, "store": False}
    if tools:
        body["tools"] = tools_for_responses(tools)
        body["tool_choice"] = tool_choice
    r = await asyncio.to_thread(_call, body)
    if "error" in r and r.get("error"):
        return {"error": r["error"]}
    summary, text, calls = [], [], []
    for o in r.get("output", []):
        if o.get("type") == "reasoning":
            summary += [s.get("text", "") for s in o.get("summary", [])]
        elif o.get("type") == "message":
            text += [c.get("text", "") for c in o.get("content", []) if c.get("type") == "output_text"]
        elif o.get("type") == "function_call":
            calls.append({"name": o.get("name"), "arguments": o.get("arguments", "")})
    u = r.get("usage", {})
    pin, pout = PRICES[MODEL_IDS[model_key]]
    cached = (u.get("input_tokens_details") or {}).get("cached_tokens", 0)
    cost = ((u.get("input_tokens", 0) - cached) * pin + cached * pin * 0.1 + u.get("output_tokens", 0) * pout) / 1e6
    return {"summary": "\n".join(summary), "text": "\n".join(text), "calls": calls, "usage": u, "cost_est": cost,
            "reasoning_tokens": (u.get("output_tokens_details") or {}).get("reasoning_tokens")}
