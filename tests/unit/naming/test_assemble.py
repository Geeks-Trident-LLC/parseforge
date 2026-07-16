import pytest

from parseforge.naming.assemble import normalize_pattern, pattern_to_cli_name


@pytest.mark.parametrize(
    "pattern, expected",
    [
        (r"show\s+version", "show-version"),
        (
            r"show\s+interface\s+(?P<var1>\S+)\s+status",
            "show-interface-var1-status",
        ),
        (
            r"show\s+ip\s+route\s+(?P<var1>\S+)",
            "show-ip-route-var1",
        ),
        (
            r"show\s+bgp\s+neighbors\s+(?P<var1>\S+)\s+advertised-routes",
            "show-bgp-neighbors-var1-advertised-routes",
        ),
        (
            r"show\s+ip\s+route\s+(?P<var1>\S+)\s+(?P<var2>\S+)",
            "show-ip-route-var1-var2",
        ),
    ],
)
def test_pattern_to_cli_name(pattern: str, expected: str) -> None:
    assert pattern_to_cli_name(pattern) == expected


@pytest.mark.parametrize(
    "pattern, expected",
    [
        (r"Show\s+Version", r"show\s+version"),
        (
            r"Show\s+Interface\s+(?P<var1>\S+)\s+Status",
            r"show\s+interface\s+(?P<var1>\S+)\s+status",
        ),
        (r"SHOW\s+CLOCK", r"show\s+clock"),
        (r"show\s+version", r"show\s+version"),
    ],
)
def test_normalize_pattern_lowercases_fixed_text_only(
    pattern: str, expected: str
) -> None:
    assert normalize_pattern(pattern) == expected


def test_normalize_pattern_does_not_corrupt_named_group_regex_classes() -> None:
    """\\S inside a named group must survive untouched — lowercasing it to
    \\s would silently change its meaning from non-whitespace to whitespace."""
    pattern = r"Show\s+Interface\s+(?P<var1>\S+)\s+Status"
    normalized = normalize_pattern(pattern)
    assert r"(?P<var1>\S+)" in normalized
