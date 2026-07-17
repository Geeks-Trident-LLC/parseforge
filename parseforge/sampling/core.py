"""Sampling stage — connect to a device and capture raw CLI output (SPEC.md §5 step 4).

Kept as a separable stage so that Mode 1 (batch: collect N samples per
command before generation) and Mode 2 (loop: sample-then-generate per
command) share the same generation/storage/validation stages and differ
only in how many samples this stage collects before handing off — see
§4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DeviceConnection:
    host: str
    username: str
    password: str
    device_type: str  # e.g. "cisco_ios", "cisco_nxos"


class Sampler(Protocol):
    """A backend capable of running a command on a device and returning raw text.

    See :mod:`parseforge.sampling.backends` for concrete implementations
    (e.g. Netmiko-backed) — none of them are required just to import this
    module, since backends carry their own optional dependencies.
    """

    def run_command(self, connection: DeviceConnection, command: str) -> str: ...


def sample(sampler: Sampler, connection: DeviceConnection, command: str) -> str:
    """Run ``command`` against ``connection`` and return raw output for input.txt."""
    return sampler.run_command(connection, command)
