from parseforge.sampling import DeviceConnection, sample

CONNECTION = DeviceConnection(
    host="10.0.0.1", username="admin", password="secret", device_type="cisco_ios"
)


class _FakeSampler:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[tuple[DeviceConnection, str]] = []

    def run_command(self, connection: DeviceConnection, command: str) -> str:
        self.calls.append((connection, command))
        return self.output


def test_sample_delegates_to_sampler_and_returns_its_output() -> None:
    sampler = _FakeSampler("show version output")

    output = sample(sampler, CONNECTION, "show version")

    assert output == "show version output"
    assert sampler.calls == [(CONNECTION, "show version")]
