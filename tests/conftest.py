"""Shared pytest configuration.

--real gates integration tests that hit real, costly external
resources (LLM API calls, live device connections) — skipped by
default so `pytest` (and CI) never spends tokens, needs credentials,
or needs network access to a device unless explicitly asked to.
"""

from __future__ import annotations

import os

import pytest

from parseforge.sampling import DeviceConnection


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--real",
        action="store_true",
        default=False,
        help="Run integration tests that hit real external resources "
        "(costs money and/or needs credentials or network access).",
    )


@pytest.fixture(scope="session")
def require_real_tests(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--real"):
        pytest.skip("real-resource test skipped — pass --real to run it")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} not set — required for real-resource tests")
    return value


@pytest.fixture(scope="session")
def anthropic_key(require_real_tests: None) -> str:
    return _require_env("ANTHROPIC_API_KEY")


@pytest.fixture(scope="session")
def deepseek_key(require_real_tests: None) -> str:
    return _require_env("DEEPSEEK_API_KEY")


@pytest.fixture(scope="session")
def openai_key(require_real_tests: None) -> str:
    return _require_env("OPENAI_API_KEY")


@pytest.fixture(scope="session")
def groq_key(require_real_tests: None) -> str:
    return _require_env("GROQ_API_KEY")


@pytest.fixture(scope="session")
def xai_key(require_real_tests: None) -> str:
    return _require_env("XAI_API_KEY")


@pytest.fixture(scope="session")
def together_key(require_real_tests: None) -> str:
    return _require_env("TOGETHER_API_KEY")


@pytest.fixture(scope="session")
def sandbox_connection(require_real_tests: None) -> DeviceConnection:
    """Generic sandbox connection — any vendor.

    No sensible default device_type exists without knowing the vendor,
    so SANDBOX_DEVICE_TYPE is required here (unlike the Cisco-specific
    fixture below, which can default it).
    """
    return DeviceConnection(
        host=_require_env("SANDBOX_HOST"),
        username=_require_env("SANDBOX_USERNAME"),
        password=_require_env("SANDBOX_PASSWORD"),
        device_type=_require_env("SANDBOX_DEVICE_TYPE"),
    )


@pytest.fixture(scope="session")
def cisco_sandbox_connection(require_real_tests: None) -> DeviceConnection:
    """Cisco-specific sandbox connection (e.g. a DevNet sandbox) — kept
    separate from the generic sandbox_connection above since other
    vendors (Juniper vLabs, Arista, ...) offer free sandboxes too, and
    tests that assert on Cisco-specific output shouldn't silently run
    against whatever vendor happens to be configured generically."""
    return DeviceConnection(
        host=_require_env("CISCO_SANDBOX_HOST"),
        username=_require_env("CISCO_SANDBOX_USERNAME"),
        password=_require_env("CISCO_SANDBOX_PASSWORD"),
        device_type=os.environ.get("CISCO_SANDBOX_DEVICE_TYPE", "cisco_ios"),
    )
