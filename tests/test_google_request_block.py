"""Google's filter refusing the REQUEST is a provider filter block, recorded the way a refused reply already is (21 Nov 2026).

On 21 Nov 2026 four Gemini 4 Neon episodes (docs/GEMINI4_PREREG.md; runs real2_neon and new_control_neon) were refused with
HTTP 403 "Gemini blocked the request: OTHER" (error_type content_policy_violation), where earlier Gemini refusals came back
as "Gemini blocked the response". The harness knew only the second form: it retried the call six times with back-off and
then ended the episode with an error, saved as incomplete. The texts below are copied from those episodes: the saved error
of runs_pod/runs/real2_neon/episodes/neon__synthetic-data-kit__safety__s0.json, and the other form the same calls raised
(runs_pod/logs/s3_neon.log, "api attempt 4/6 failed (403)").
"""
import asyncio
import types

import pytest

from sfe import agent, api
from sfe.config import MODELS

# word for word from the episode file's "error" field (after the harness's "RuntimeError: no choices: " prefix)
SAVED_ERROR = ("RuntimeError: no choices: {'message': 'Gemini blocked the request: OTHER', 'code': 403, 'metadata': "
               "{'error_type': 'content_policy_violation', 'provider_code': 'OTHER'}}")
ERROR_BODY = {"message": "Gemini blocked the request: OTHER", "code": 403,
              "metadata": {"error_type": "content_policy_violation", "provider_code": "OTHER"}}


class PermissionDeniedError(Exception):
    """Stands in for openai.PermissionDeniedError: same class name, status code and message as in the machine's log."""
    status_code = 403


class FakeClient:
    """An OpenRouter client whose every call is refused in one of the two forms seen on 21 Nov 2026."""

    def __init__(self, form: str):
        self.calls = 0
        self.form = form
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    async def create(self, **kw):
        self.calls += 1
        if self.form == "no choices":
            return types.SimpleNamespace(choices=[], error=ERROR_BODY, usage=None)
        raise PermissionDeniedError("Error code: 403 - Gemini blocked the request: OTHER")


@pytest.fixture
def no_waiting(monkeypatch):
    async def instant(_s):
        return None
    monkeypatch.setattr(api.asyncio, "sleep", instant)       # the back-off between attempts, so a failure is quick


def test_the_saved_error_text_is_the_no_choices_form():
    assert SAVED_ERROR == f"RuntimeError: no choices: {ERROR_BODY}"


@pytest.mark.parametrize("form", ["no choices", "403 exception"])
def test_a_request_blocked_by_google_is_a_filter_refusal_not_an_error(monkeypatch, no_waiting, form):
    fake = FakeClient(form)
    monkeypatch.setattr(api, "client", lambda: fake)
    r = asyncio.run(api.chat(MODELS["neon"], [{"role": "user", "content": "u"}]))
    # the same Reply a blocked response gives (sfe/api.py): empty, finish reason content_filter, no cost, no error
    assert r.error is None
    assert (r.text, r.tool_calls, r.finish_reason, r.provider, r.cost_usd) == ("", [], "content_filter", "Google (blocked)", 0.0)
    assert fake.calls == 1                                    # not retried six times


def test_three_request_blocks_in_a_row_block_the_turn(monkeypatch, no_waiting):
    """Through the agent's turn loop: asked again as a user would, then the turn is blocked, with no error recorded."""
    fake = FakeClient("no choices")
    monkeypatch.setattr(api, "client", lambda: fake)
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    tr = asyncio.run(agent.run_turn(MODELS["neon"], msgs, None, 5, lambda *_: None))
    assert tr["filter_blocked"] and tr["filter_refusals"] == agent.FILTER_ATTEMPTS and tr["errors"] == []
    assert fake.calls == agent.FILTER_ATTEMPTS
    assert [m["role"] for m in msgs] == ["system", "user"]


def test_other_errors_are_still_retried(monkeypatch, no_waiting):
    """A rate limit (429) is not a filter block: it is retried and, if it never clears, reported as an error."""
    class RateLimitError(Exception):
        status_code = 429

    class Busy(FakeClient):
        async def create(self, **kw):
            self.calls += 1
            raise RateLimitError("Error code: 429 - Provider returned error")

    fake = Busy("busy")
    monkeypatch.setattr(api, "client", lambda: fake)
    r = asyncio.run(api.chat(MODELS["neon"], [{"role": "user", "content": "u"}]))
    assert r.error and r.finish_reason is None and fake.calls == api.MAX_ATTEMPTS
