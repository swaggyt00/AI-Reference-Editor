"""Conservative application-level recovery for Gemini overloads.

The Google SDK already retries some failures internally. We allow just ONE
additional end-to-end attempt after a confirmed transient 502/503/504. This is
bounded and does not retry 429 quota errors, invalid keys or unsafe uploads.
No automatic model/provider switching or billable job cloning.
"""
from __future__ import annotations
import random
import time

# Video-understanding models documented by Google's model/pricing pages.
# Availability on a specific free-tier API key is NOT guaranteed.
DEFAULT_MODEL = "gemini-3.6-flash"
SUPPORTED_MODELS = (DEFAULT_MODEL, "gemini-3.8-flash", "gemini-3.5-flash-lite")
RETRY_STATUSES = {502, 503, 504}


def status_code(error):
    """Extract status without printing raw errors which may contain key material."""
    for candidate in (error, getattr(error, "response", None)):
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


def call_with_overload_retry(operation, *, on_retry=None, sleep=time.sleep,
                             jitter=random.uniform):
    """One additional attempt after the SDK's own retries, only for server 5xx.

    The callback receives a safe retry count/status, never an exception string.
    Do not wrap upload/delete endpoints here because retries there can create
    duplicated remote files or accidentally repeat destructive actions.
    """
    for attempt in (1, 2):
        try:
            return operation()
        except Exception as exc:
            code = status_code(exc)
            if attempt == 2 or code not in RETRY_STATUSES:
                raise
            if on_retry:
                on_retry(attempt, code)
            sleep(1.5 + max(0., min(0.8, float(jitter(0., 0.8)))))


def validate_model(model):
    if model not in SUPPORTED_MODELS:
        raise ValueError("Unsupported Gemini model for AI video analysis.")
    return model
