"""Errors the LLM layer raises, so callers can report them as errors.

V1 turned every provider failure into an empty answer, and the answer step
then said "Source Not Found": a timeout looked like a document that lacks the
fact (audit P1-8). Now a failed call raises ``LLMError`` with a ``kind`` the
API can turn into a proper status code and a message the user can act on.
"""

from __future__ import annotations


class LLMError(RuntimeError):
    """A model call that failed after its retries (or ran out of time)."""

    #: kind -> HTTP status the API answers with
    STATUS = {
        "timeout": 504,
        "deadline": 504,
        "network": 502,
        "rate_limit": 429,
        "auth": 502,
        "bad_request": 502,
        "provider": 502,
    }

    def __init__(self, message: str, *, kind: str = "provider", provider: str = "", status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.provider = provider
        self.status = status

    @property
    def http_status(self) -> int:
        return self.STATUS.get(self.kind, 502)

    def user_message(self) -> str:
        who = self.provider or "the model provider"
        return {
            "timeout": f"{who} did not answer in time. Please try again.",
            "deadline": "The answer took longer than the time limit. Please try again.",
            "network": f"Could not reach {who} (network error). Please try again.",
            "rate_limit": f"{who} is rate-limiting requests. Please wait a moment and try again.",
            "auth": f"{who} rejected the API key. An administrator needs to check it.",
            "bad_request": f"{who} rejected the request ({self}).",
        }.get(self.kind, f"{who} returned an error ({self}).")


class ModelNotAvailableError(ValueError):
    """The requested model is unknown, not allowed, or has no API key here."""


class SpendingCapError(RuntimeError):
    """A monthly spending cap is reached; the question is not sent to a model."""
