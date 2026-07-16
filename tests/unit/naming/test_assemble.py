import pytest

from parseforge.naming.assemble import pattern_to_cli_name


@pytest.mark.parametrize(
    "pattern, expected",
    [
        (r"(?i)show\s+version", "show-version"),
        (
            r"(?i)show\s+interface\s+(?P<var1>\S+)\s+status",
            "show-interface-var1-status",
        ),
        (
            r"(?i)show\s+ip\s+route\s+(?P<var1>\S+)",
            "show-ip-route-var1",
        ),
        (
            r"(?i)show\s+bgp\s+neighbors\s+(?P<var1>\S+)\s+advertised-routes",
            "show-bgp-neighbors-var1-advertised-routes",
        ),
        (
            r"(?i)show\s+ip\s+route\s+(?P<var1>\S+)\s+(?P<var2>\S+)",
            "show-ip-route-var1-var2",
        ),
    ],
)
def test_pattern_to_cli_name(pattern: str, expected: str) -> None:
    assert pattern_to_cli_name(pattern) == expected
