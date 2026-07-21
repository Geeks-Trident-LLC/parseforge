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


def reference_summary_path(store_root: Path) -> Path:
    """Cross-cli-name ratio report aggregating every reference.json under
    the integration tier (see
    :func:`parseforge.integration.write_reference_summary`)."""
    return tier_root(store_root, INTEGRATION) / "reference-summary.json"


def discover_device_keys(store_root: Path) -> list[DeviceKey]:
    """Every (vendor, family, os, cli-name) that currently has a trials/
    directory — walks trials/ four levels deep. Used by promotion to find
    every case worth refreshing, not just ones already integrated."""
    trials_root = tier_root(store_root, TRIALS)
    if not trials_root.exists():
        return []

    keys = []
    for vendor_dir in sorted(d for d in trials_root.iterdir() if d.is_dir()):
        for family_dir in sorted(d for d in vendor_dir.iterdir() if d.is_dir()):
            for os_dir in sorted(d for d in family_dir.iterdir() if d.is_dir()):
                for cli_name_dir in sorted(d for d in os_dir.iterdir() if d.is_dir()):
                    keys.append(
                        DeviceKey(
                            vendor=vendor_dir.name,
                            family=family_dir.name,
                            os=os_dir.name,
                            cli_name=cli_name_dir.name,
                        )
                    )
    return keys


def promoted_data_dir(store_root: Path, key: DeviceKey, group_id: str) -> Path:
    """Where a promoted group's sample(-suffix).txt / records(-suffix).json
    live, alongside (not inside) template(-suffix).textfsm."""
    return authoritative_group_dir(store_root, key, group_id) / "data"


def golden_hash_path(store_root: Path, key: DeviceKey, group_id: str) -> Path:
    """sha256 of the currently-promoted template.textfsm content, updated on
    every promotion into this group (regardless of mode/suffix) — the
    baseline future drift checks compare production samples against."""
    return authoritative_group_dir(store_root, key, group_id) / "golden.hash"


def artifact_path(store_root: Path, key: DeviceKey, group_id: str) -> Path:
    """Snapshot describing the most recent promotion into this group (who,
    when, mode, match rate, source trial) — distinct from promotion-log.json,
    which is the append-only history across every promotion event."""
    return authoritative_group_dir(store_root, key, group_id) / "artifact.json"


def promotion_log_path(store_root: Path, key: DeviceKey) -> Path:
    """Append-only promotion history for a cli-name, shared across all of
    its groups (each entry records its own group_id)."""
    return authoritative_dir(store_root, key) / "promotion-log.json"


def authoritative_summary_path(store_root: Path) -> Path:
    """Project-wide snapshot of the most recent promotion run — what got
    promoted, what didn't clear its gate, and (for USER_REVIEWED) any
    requested case that doesn't exist. Overwritten every run; history lives
    in each cli-name's own promotion-log.json instead."""
    return tier_root(store_root, AUTHORITATIVE) / "authoritative-summary.json"
