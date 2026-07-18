"""Live integration test for NetmikoSampler against a real Cisco device.

Skipped by default — run with `pytest --real` and CISCO_SANDBOX_HOST /
CISCO_SANDBOX_USERNAME / CISCO_SANDBOX_PASSWORD set
(CISCO_SANDBOX_DEVICE_TYPE optional, defaults to "cisco_ios"). Opens a
real SSH connection — e.g. a Cisco DevNet sandbox
(https://developer.cisco.com/site/sandbox/).

Uses the Cisco-specific fixture (not the generic sandbox_connection)
since the commands and assertions below are Cisco IOS-flavored.
"""

from __future__ import annotations

import pytest

pytest.importorskip(
    "netmiko", reason="netmiko is an optional extra (parseforge[sampling])"
)

from parseforge.sampling import DeviceConnection, sample  # noqa: E402
from parseforge.sampling.backends import NetmikoSampler  # noqa: E402

pytestmark = pytest.mark.real


def test_run_command_show_version(cisco_sandbox_connection: DeviceConnection) -> None:
    output = sample(NetmikoSampler(), cisco_sandbox_connection, "show version")
    assert output
    assert "cisco" in output.lower()


def test_run_command_show_clock(cisco_sandbox_connection: DeviceConnection) -> None:
    output = sample(NetmikoSampler(), cisco_sandbox_connection, "show clock")
    assert output.strip()


def test_separate_calls_open_independent_connections(
    cisco_sandbox_connection: DeviceConnection,
) -> None:
    """NetmikoSampler holds no session state between calls (see its
    docstring) — two calls in a row must both succeed independently,
    not rely on a connection left open by the first."""
    sampler = NetmikoSampler()
    first = sample(sampler, cisco_sandbox_connection, "show version")
    second = sample(sampler, cisco_sandbox_connection, "show clock")
    assert first
    assert second
