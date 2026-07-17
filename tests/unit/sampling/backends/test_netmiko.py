import pytest

pytest.importorskip(
    "netmiko", reason="netmiko is an optional extra (parseforge[sampling])"
)

from parseforge.sampling.backends.netmiko import NetmikoSampler  # noqa: E402
from parseforge.sampling.core import DeviceConnection  # noqa: E402

CONNECTION = DeviceConnection(
    host="10.0.0.1", username="admin", password="secret", device_type="cisco_ios"
)


class _FakeNetmikoConnection:
    def __init__(self, **device: object) -> None:
        self.device = device
        self.commands: list[str] = []
        self.entered = False
        self.exited = False

    def __enter__(self) -> "_FakeNetmikoConnection":
        self.entered = True
        return self

    def __exit__(self, *exc: object) -> bool:
        self.exited = True
        return False

    def send_command(self, command: str) -> str:
        self.commands.append(command)
        return f"output-of-{command}"


def test_run_command_connects_sends_command_and_disconnects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[_FakeNetmikoConnection] = []

    def _fake_connect_handler(**device: object) -> _FakeNetmikoConnection:
        conn = _FakeNetmikoConnection(**device)
        created.append(conn)
        return conn

    monkeypatch.setattr(
        "parseforge.sampling.backends.netmiko.ConnectHandler", _fake_connect_handler
    )

    output = NetmikoSampler().run_command(CONNECTION, "show version")

    assert output == "output-of-show version"
    assert len(created) == 1
    conn = created[0]
    assert conn.device == {
        "device_type": "cisco_ios",
        "host": "10.0.0.1",
        "username": "admin",
        "password": "secret",
    }
    assert conn.commands == ["show version"]
    assert conn.entered is True
    assert conn.exited is True
