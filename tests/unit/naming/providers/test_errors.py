import pytest

from parseforge.naming.providers.errors import (
    error_type_slug,
    format_llm_error_reason,
    is_retryable,
)


@pytest.mark.parametrize(
    "name, expected_slug",
    [
        ("BadRequestError", "bad_request"),
        ("AuthenticationError", "authentication"),
        ("RateLimitError", "rate_limit"),
        ("InternalServerError", "internal_server"),
        ("APIConnectionError", "api_connection"),
    ],
)
def test_error_type_slug(name: str, expected_slug: str) -> None:
    exc = type(name, (Exception,), {})("boom")
    assert error_type_slug(exc) == expected_slug


@pytest.mark.parametrize(
    "name, expected",
    [
        ("BadRequestError", False),
        ("AuthenticationError", False),
        ("PermissionDeniedError", False),
        ("NotFoundError", False),
        ("ConflictError", False),
        ("UnprocessableEntityError", False),
        ("RequestTooLargeError", False),
        ("RateLimitError", True),
        ("InternalServerError", True),
        ("OverloadedError", True),
        ("APIConnectionError", True),
        ("APITimeoutError", True),
    ],
)
def test_is_retryable(name: str, expected: bool) -> None:
    exc = type(name, (Exception,), {})("boom")
    assert is_retryable(exc) is expected


def test_format_llm_error_reason() -> None:
    exc = type("BadRequestError", (Exception,), {})("malformed request")
    assert format_llm_error_reason(exc) == "LLM-ERROR-bad_request-malformed request"
