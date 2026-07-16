"""Shared pytest configuration.

--real gates integration tests that make real, costly API calls — skipped
by default so `pytest` (and CI) never spends tokens or needs credentials
unless explicitly asked to.
"""

from __future__ import annotations

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--real",
        action="store_true",
        default=False,
        help="Run integration tests that make real API calls "
        "(costs money, needs credentials).",
    )


@pytest.fixture(scope="session")
def require_real_tests(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--real"):
        pytest.skip("real-API test skipped — pass --real to run it")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} not set — required for real-API tests")
    return value


@pytest.fixture(scope="session")
def anthropic_key(require_real_tests: None) -> str:
    return _require_env("ANTHROPIC_API_KEY")
