"""Verify parseforge's top-level public API (parseforge/api.py,
re-exported at the package root) stays importable and in sync."""

from __future__ import annotations

import parseforge
from parseforge import api


def test_root_all_is_api_all_plus_version() -> None:
    assert set(parseforge.__all__) == set(api.__all__) | {"version", "__version__"}


def test_every_root_export_is_actually_importable() -> None:
    for name in parseforge.__all__:
        assert hasattr(parseforge, name), f"parseforge.{name} is missing"


def test_every_api_export_is_actually_importable() -> None:
    for name in api.__all__:
        assert hasattr(api, name), f"parseforge.api.{name} is missing"


def test_naming_and_generation_token_usage_are_distinct_types() -> None:
    assert parseforge.NamingTokenUsage is not parseforge.GenerationTokenUsage
