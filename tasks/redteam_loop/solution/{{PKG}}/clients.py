"""Deterministic mock chat-model clients standing in for the real {{PROBER}}, {{RESPONDER}} and {{SCORER}} APIs."""
from __future__ import annotations

SUCCESS_MARKER = "{{MARKER}}"


class TransientError(Exception):
    """A retryable API failure (timeout, 5xx, dropped connection)."""


class RateLimitError(TransientError):
    """HTTP 429. Retryable, like any TransientError."""


class PermanentError(Exception):
    """A non-retryable API failure (bad request, auth error, context too long)."""


class MockClient:
    """Returns the replies in `script` in order, cycling when the script is exhausted. If `fail_every` is set,
    every `fail_every`-th call raises TransientError instead (consuming no reply); a script entry that is an
    exception instance is raised. `calls` counts every call; `received` keeps each call's messages."""

    def __init__(self, script: list, fail_every: int | None = None):
        if not script:
            raise ValueError("MockClient needs a non-empty script")
        self.script = list(script)
        self.fail_every = fail_every
        self.calls = 0
        self.received: list[list[dict]] = []
        self._pos = 0

    def complete(self, messages: list[dict]) -> str:
        self.calls += 1
        self.received.append(list(messages))
        if self.fail_every and self.calls % self.fail_every == 0:
            raise TransientError(f"mock transient failure on call {self.calls}")
        item = self.script[self._pos % len(self.script)]
        self._pos += 1
        if isinstance(item, BaseException):
            raise item
        return item


class MarkerScorerClient(MockClient):
    """Mock {{SCORER}}: replies "1" when the last message contains SUCCESS_MARKER, else "0"."""

    def __init__(self, fail_every: int | None = None):
        super().__init__(["0"], fail_every=fail_every)

    def complete(self, messages: list[dict]) -> str:
        super().complete(messages)
        return "1" if SUCCESS_MARKER in messages[-1]["content"] else "0"
