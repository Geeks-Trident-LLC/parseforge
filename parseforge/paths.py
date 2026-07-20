"""Storage layout — three-tier promotion path resolution (SPEC.md §3).

Shared path prefix under all three tiers:
    <vendor>/<device-family>/<os>/<cli-name>/

Deliberately no ``<version>`` segment: a cli-name's output structure
usually doesn't change across minor OS versions, and when it does, that's
exactly the variance :mod:`parseforge.integration`'s group clustering is
built to catch — lumping versions together gives more evidence per group
instead of silently fragmenting it across per-version directories. The
version a trial was sampled from is recorded in that trial's
``summary.json`` (``command_info.version``) instead.

Use hyphenated OS family names (``ios-xe``, ``nx-os``) once multiple
Cisco OS families share the tree, per §3's note.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

TRIALS = "trials"
INTEGRATION = "integration"
AUTHORITATIVE = "authoritative"

DEFAULT_STORE_ROOT = Path.home() / ".parseforge" / "tests"


@dataclass(frozen=True)
class DeviceKey:
    """Identifies a template family: vendor/device-family/os/cli-name."""

    vendor: str
    family: str
    os: str
    cli_name: str

    def relative_path(self) -> Path:
        return Path(self.vendor, self.family, self.os, self.cli_name)


def tier_root(store_root: Path, tier: str) -> Path:
    if tier not in (TRIALS, INTEGRATION, AUTHORITATIVE):
        raise ValueError(f"unknown tier: {tier!r}")
    return store_root / tier


def tier_path(store_root: Path, tier: str, key: DeviceKey) -> Path:
    """Resolve the directory for ``key`` under the given tier."""
    return tier_root(store_root, tier) / key.relative_path()


def new_run_id() -> str:
    """Timestamp+shortid run identifier (§3.1) — chronological, collision-safe."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shortid = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{timestamp}-{shortid}"


def trial_run_dir(store_root: Path, key: DeviceKey, run_id: str | None = None) -> Path:
    """Directory for a single trial run: trials/.../<cli-name>/<run-id>/."""
    run_id = run_id or new_run_id()
    return tier_path(store_root, TRIALS, key) / run_id


def integration_dir(store_root: Path, key: DeviceKey) -> Path:
    """Integration tier directory for a cli-name (§3.2) — holds
    reference.json and the clustered group<J>-template<I>.textfsm files
    (see :mod:`parseforge.integration`)."""
    return tier_path(store_root, INTEGRATION, key)


def authoritative_dir(store_root: Path, key: DeviceKey) -> Path:
    """The approved, in-production directory for a cli-name (§3.3)."""
    return tier_path(store_root, AUTHORITATIVE, key)


def authoritative_group_dir(store_root: Path, key: DeviceKey, group_id: str) -> Path:
    """Directory for one promoted group variant under a cli-name — multiple
    groups can coexist per cli-name when output legitimately varies by
    hardware/firmware (§6)."""
    return authoritative_dir(store_root, key) / group_id
