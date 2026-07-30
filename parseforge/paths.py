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
    """The approved, in-production directory for a cli-name (§3.3) — final,
    delivery-ready content only. Every simultaneously-valid variant for a
    cli-name (hardware/firmware variance, §6) lives directly in this one
    flat directory, distinguished by filename (template.textfsm,
    template-v2.textfsm, ...) rather than a per-variant subdirectory — see
    :mod:`parseforge.promotion`."""
    return tier_path(store_root, AUTHORITATIVE, key)


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


def promoted_data_dir(store_root: Path, key: DeviceKey) -> Path:
    """Where a promoted variant's sample(-suffix).txt /
    records(-suffix).json live, alongside (not inside) each cli-name's
    template(-suffix).textfsm."""
    return authoritative_dir(store_root, key) / "data"


def golden_hash_path(store_root: Path, key: DeviceKey) -> Path:
    """sha256 of whichever template was most recently promoted for this
    cli-name — a single, unsuffixed file (not one per variant), always
    reflecting the latest promotion regardless of which group/suffix
    triggered it. The baseline future drift checks compare against."""
    return authoritative_dir(store_root, key) / "golden.hash"


def artifact_path(store_root: Path, key: DeviceKey) -> Path:
    """Snapshot describing the most recent promotion for this cli-name —
    a single, unsuffixed file (not one per variant), mirroring
    golden.hash's "always latest" semantics."""
    return authoritative_dir(store_root, key) / "artifact.json"


def authoritative_history_dir(store_root: Path, key: DeviceKey) -> Path:
    """Where a promoted file's prior content is archived just before it
    gets overwritten by a *different* promotion into the same slot (§3.3)
    — e.g. re-running promote_auto() after new trials change which variant
    is representative. Archived filenames are ``<stem>-<run-id>.<ext>``
    (e.g. ``template-20260721-083901-ab12cd.textfsm``,
    ``template-v2-20260721-090512-ef34gh.textfsm``), so the slot a given
    history entry used to belong to stays identifiable even with multiple
    simultaneously-valid variants. Nothing is archived when a promotion
    writes byte-identical content — see :mod:`parseforge.promotion`."""
    return authoritative_dir(store_root, key) / "history"


def authoritative_summary_path(store_root: Path) -> Path:
    """Project-wide snapshot of the most recent promotion run — what got
    promoted, what didn't clear its gate, and (for USER_REVIEWED) any
    requested case that doesn't exist. Overwritten every run — metadata
    history across every promotion event lives in authoritative-log.json,
    and prior file *content* lives in each cli-name's own history/."""
    return tier_root(store_root, AUTHORITATIVE) / "authoritative-summary.json"


def authoritative_log_path(store_root: Path) -> Path:
    """Append-only promotion history across every cli-name and every
    promotion event ever — one project-wide file (mirroring
    reference-summary.json's one-file pattern) rather than one log per
    cli-name, since each entry already records which case/variant it
    belongs to."""
    return tier_root(store_root, AUTHORITATIVE) / "authoritative-log.json"
