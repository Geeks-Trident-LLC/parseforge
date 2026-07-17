"""Netmiko-backed Sampler implementation.

Requires the optional ``sampling`` extra (``pip install parseforge[sampling]``)
— nothing else in :mod:`parseforge.sampling` needs netmiko, only this module.
"""

from __future__ import annotations

from typing import cast

from netmiko import ConnectHandler

from ..core import DeviceConnection


class NetmikoSampler:
    """Runs a single command on a device via Netmiko and returns its raw output.

    Opens a new SSH connection per call and closes it on return — this
    pipeline stage samples a command at a time rather than holding a
    session open across many, so there's no connection pooling here.
    """

    def run_command(self, connection: DeviceConnection, command: str) -> str:
        device = {
            "device_type": connection.device_type,
            "host": connection.host,
            "username": connection.username,
            "password": connection.password,
        }
        with ConnectHandler(**device) as conn:
            # send_command()'s stub returns str | list | dict because it can
            # emit structured output when a use_textfsm/use_genie/use_ttp
            # flag is passed — we never pass one, so this is always a str.
            return cast(str, conn.send_command(command))
