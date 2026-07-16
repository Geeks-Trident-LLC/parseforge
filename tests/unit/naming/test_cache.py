from pathlib import Path

from parseforge.naming.cache import NameIndex


def test_match_returns_none_on_empty_index(tmp_path: Path) -> None:
    index = NameIndex(tmp_path / ".cli-name.json")
    assert index.match("show version") is None


def test_add_then_match_finds_entry(tmp_path: Path) -> None:
    index = NameIndex(tmp_path / ".cli-name.json")
    index.add("show-version", r"(?i)show\s+version")
    assert index.match("show version") == "show-version"
    assert index.match("SHOW VERSION") == "show-version"
    assert index.match("show clock") is None


def test_save_and_reload_roundtrips(tmp_path: Path) -> None:
    path = tmp_path / ".cli-name.json"
    index = NameIndex(path)
    index.add("show-version", r"(?i)show\s+version")
    index.save()

    assert path.exists()
    reloaded = NameIndex(path)
    assert reloaded.match("show version") == "show-version"
