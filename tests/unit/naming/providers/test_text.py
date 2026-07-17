import pytest

from parseforge.naming.providers.text import extract_pattern


@pytest.mark.parametrize(
    "raw, expected",
    [
        (r"show\s+version", r"show\s+version"),
        ("```\n" + r"show\s+version" + "\n```", r"show\s+version"),
        ("```regex\n" + r"show\s+version" + "\n```", r"show\s+version"),
        ("  " + r"show\s+version" + "  \n", r"show\s+version"),
        (r"show\s+version" + "\nsome trailing explanation", r"show\s+version"),
    ],
)
def test_extract_pattern_strips_fences_and_noise(raw: str, expected: str) -> None:
    assert extract_pattern(raw) == expected
