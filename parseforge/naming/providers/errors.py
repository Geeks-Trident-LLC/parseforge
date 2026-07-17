"""Shared LLM-error classification for provider RegexBuilder implementations.

Both the ``anthropic`` and ``openai`` SDKs raise near-identical exception
class names for the same HTTP-status-code failure modes (BadRequestError,
AuthenticationError, RateLimitError, ...), so classification here is done
by class name rather than importing either SDK's specific exception
classes — this stays correct regardless of which provider raised it.
"""

from __future__ import annotations

import re

# Client-side errors: the request itself is broken (malformed input, bad
# credentials, wrong resource, request too large, ...). Retrying the exact
# same request fails the exact same way, so these are not worth retrying —
# the caller should stop rather than burn another attempt.
_NON_RETRYABLE = frozenset(
    {
        "BadRequestError",
        "AuthenticationError",
        "PermissionDeniedError",
        "NotFoundError",
        "ConflictError",
        "UnprocessableEntityError",
        "RequestTooLargeError",
    }
)

# Two-pass camelCase -> snake_case that keeps acronym runs together, e.g.
# "APIConnectionError" -> "api_connection" rather than "a_p_i_connection":
# first split before a Capital+lowercase run (word boundaries), then split
# between a lowercase/digit and a following Capital (acronym -> word).
_WORD_BOUNDARY_1 = re.compile(r"(.)([A-Z][a-z]+)")
_WORD_BOUNDARY_2 = re.compile(r"([a-z0-9])([A-Z])")


def error_type_slug(exc: BaseException) -> str:
    """
    >>> error_type_slug(ValueError())
    'value'
    >>> error_type_slug(type("APIConnectionError", (Exception,), {})())
    'api_connection'
    """
    name = type(exc).__name__
    if name.endswith("Error"):
        name = name[: -len("Error")]
    name = _WORD_BOUNDARY_1.sub(r"\1_\2", name)
    name = _WORD_BOUNDARY_2.sub(r"\1_\2", name)
    return name.lower()


def is_retryable(exc: BaseException) -> bool:
    """False for errors where retrying the same request can't succeed."""
    return type(exc).__name__ not in _NON_RETRYABLE


def format_llm_error_reason(exc: BaseException) -> str:
    """
    >>> format_llm_error_reason(ValueError("bad input"))
    'LLM-ERROR-value-bad input'
    """
    return f"LLM-ERROR-{error_type_slug(exc)}-{exc}"
