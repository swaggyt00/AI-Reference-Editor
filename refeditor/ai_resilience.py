"""Bounded recovery for transient Google Gemini HTTP and transport failures.

The Python GenAI SDK retries many 5xx errors already, but raw HTTPX network
disconnects can bypass it. Only repeat content generation and Files API GET.
NEVER blindly repeat uploads, deletion, other side effects, 429, or auth errors.
"""
from __future__ import annotations

import random
import time

DEFAULT_MODEL = "gemini-3.6-flash"
SUPPORTED_MODELS = (DEFAULT_MODEL, "gemini-3.8-flash", "gemini-3.5-flash-lite")
RETRY_STATUSES = {502, 503, 504}
NETWORK_ERRORS = frozenset({
    "RemoteProtocolError", "ReadError", "ConnectError", "CloseError",
    "ReadTimeout", "ConnectTimeout", "WriteTimeout", "PoolTimeout",
})


class GeminiStepFailure(RuntimeError):
    """Safe user-facing stage with chained original exception preserved for logs."""

    def __init__(self, stage):
        self.stage = str(stage)[:90]
        super().__init__("Ошибка Gemini на этапе: " + self.stage)


def root_cause(error):
    """At most four chained exceptions, without ever exposing their raw text."""
    seen = set()
    exc = error
    for _ in range(4):
        if exc is None or id(exc) in seen:
            break
        seen.add(id(exc))
        if isinstance(exc, GeminiStepFailure) and exc.__cause__ is not None:
            exc = exc.__cause__
            continue
        return exc
    return error


def status_code(error):
    """Extract a real HTTP status; plain errors have no HTTP code."""
    for candidate in (root_cause(error), getattr(root_cause(error), "response", None)):
        if candidate is None:
            continue
        for field in ("code", "status_code"):
            value = getattr(candidate, field, None)
            if value is None:
                continue
            try:
                if type(value) in (int, str):
                    return int(value)
            except (TypeError, ValueError):
                pass
    return None


def is_transient_network_error(error):
    """Match only known transport library exceptions, not generic RuntimeError.

    RemoteProtocolError means a remote peer/proxy closed the HTTP connection.
    It is not evidence of invalid credentials, a model refusal, or a bad video.
    """
    cause = root_cause(error)
    cls = type(cause)
    return (cls.__name__ in NETWORK_ERRORS
            and cls.__module__.split(".", 1)[0] in ("httpx", "httpcore"))


def retry_label(code):
    return f"HTTP {code}" if isinstance(code, int) else "обрыв сети"


def call_with_overload_retry(operation, *, on_retry=None, sleep=time.sleep,
                             jitter=random.uniform):
    """Bounded retry for repeatable Gemini reads/inference ONLY.

    5xx: 2 total attempts after SDK retries. Transport disconnects/timeouts:
    up to 3 attempts, with increasing delays and jitter. 429, auth failures,
    and all other exceptions immediately escape.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return operation()
        except Exception as exc:
            code = status_code(exc)
            network = is_transient_network_error(exc)
            maximum = 3 if network else 2 if code in RETRY_STATUSES else 1
            if attempt >= maximum:
                raise
            label = "network" if network else code
            if on_retry:
                on_retry(attempt, label)
            # exponential backoff + capped random jitter; no infinite loop.
            delay = min(8.0, 1.5 * (2 ** (attempt - 1)))
            sleep(delay + max(0.0, min(0.8, float(jitter(0., 0.8)))))


def validate_model(model):
    if model not in SUPPORTED_MODELS:
        raise ValueError("Unsupported Gemini model for AI video analysis.")
    return model
