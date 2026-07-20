"""Integration — cluster trials for a cli-name into output-schema groups
(SPEC.md §3.2, §5 step 8; §6 multi-variant note).

Unlike §3.2's original single "common-result" winner, a cli-name's output
can legitimately vary by hardware/firmware (§6). ``build_integration``
groups every trial for a cli-name by the field-key signature of its parsed
records, and within a group further distinguishes byte-identical template
variants from divergent ones. This is pure evidence gathering — no
promotion decision is made or stored here (see :mod:`parseforge.promotion`
for that, which reads ``reference.json`` back out).

Only trials whose own summary.json says ``passed: true`` are eligible —
see :func:`_trial_passed`. A trial can fail for reasons a template/sample
re-parse alone wouldn't catch (e.g. a truncated, not-ready generation
whose partial output still happens to self-parse), so that stored verdict
is trusted rather than re-derived.

``build_integration`` is a full rebuild each call: every trial run-dir for
the cli-name is rescanned and ``reference.json`` is regenerated from
scratch, rather than incrementally diffed against its prior contents. A new
trial is only ever compared against the (small) set of distinct groups
already found, not every past trial, so this costs the same either way and
avoids partial-state bugs. Group/variant numbering stays deterministic
because trial run-dirs are iterated in chronological run-id order.

``reference.json`` is ``{total_case_count, groups: {group_id: {keys,
sample_path, group_case_count, variants}}}`` — ``total_case_count`` and
each group's ``group_case_count`` are snapshots from that same rebuild
(as fresh as everything else in the file), included so match rate is
readable without re-globbing trials/. :func:`build_reference_summary`
turns those counts into ratios across every cli-name in one report;
:mod:`parseforge.promotion` still recomputes its own count independently
at decision time rather than trusting either snapshot.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from parseforge import paths, validation


@dataclass(frozen=True)
class ReferenceVariant:
    template_path: str
    exact_template_count: int
    exact_records_count: int


@dataclass(frozen=True)
class ReferenceGroup:
    keys: list[str]
    sample_path: str
    variants: dict[str, ReferenceVariant] = field(default_factory=dict)

    @property
    def group_case_count(self) -> int:
        """Total trials belonging to this group — the sum of every
        variant's exact_template_count. A property (not a stored field) so
        it can never drift out of sync with ``variants``."""
        return sum(v.exact_template_count for v in self.variants.values())


Reference = dict[str, ReferenceGroup]


def _load_reference(path: Path) -> Reference:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    reference: Reference = {}
    for group_id, group_raw in raw.get("groups", {}).items():
        variants = {
            variant_id: ReferenceVariant(**variant_raw)
            for variant_id, variant_raw in group_raw["variants"].items()
        }
        reference[group_id] = ReferenceGroup(
            keys=group_raw["keys"],
            sample_path=group_raw["sample_path"],
            variants=variants,
        )
    return reference


def _save_reference(path: Path, reference: Reference, total_case_count: int) -> None:
    """Write reference.json as ``{total_case_count, groups}``.

    ``total_case_count`` is a snapshot from the same trial scan that
    produced ``groups`` below it — as fresh as the rest of this file, and
    included purely so a reader (or :func:`build_reference_summary`) can
    compute match rate without re-globbing trials/. Promotion decisions
    still recompute their own count independently at decision time (see
    :mod:`parseforge.promotion`) rather than trusting this snapshot.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        "total_case_count": total_case_count,
        "groups": {
            group_id: {
                "keys": group.keys,
                "sample_path": group.sample_path,
                "group_case_count": group.group_case_count,
                "variants": {
                    variant_id: asdict(variant)
                    for variant_id, variant in group.variants.items()
                },
            }
            for group_id, group in reference.items()
        },
    }
    path.write_text(
        json.dumps(serializable, indent=2, sort_keys=True), encoding="utf-8"
    )


def build_integration(store_root: Path, key: paths.DeviceKey) -> Reference:
    """Rebuild the group clustering for ``key.cli_name`` from every trial
    currently under ``trials/<vendor>/.../<cli-name>/``, and persist it to
    ``integration/.../<cli-name>/reference.json``.
    """
    trials_dir = paths.tier_path(store_root, paths.TRIALS, key)
    integration_dir = paths.integration_dir(store_root, key)
    integration_dir.mkdir(parents=True, exist_ok=True)

    reference: Reference = {}
    if not trials_dir.exists():
        _save_reference(
            integration_dir / "reference.json", reference, total_case_count=0
        )
        return reference

    run_dirs = sorted(d for d in trials_dir.iterdir() if d.is_dir())

    for run_dir in run_dirs:
        if not _trial_passed(run_dir):
            continue

        template_path = run_dir / "derive" / "template.textfsm"
        sample_path = run_dir / "samples" / "sample.txt"
        if not template_path.exists() or not sample_path.exists():
            continue

        template_text = template_path.read_text(encoding="utf-8")
        sample_text = sample_path.read_text(encoding="utf-8")

        parsed = validation.parse(template_text, sample_text)
        if not parsed.passed or not parsed.records:
            continue

        record_keys = sorted(parsed.records[0].keys())
        group_id = _find_matching_group(reference, record_keys)
        if group_id is None:
            group_id = f"group{len(reference) + 1}"
            reference[group_id] = ReferenceGroup(
                keys=record_keys, sample_path=str(sample_path), variants={}
            )

        group = reference[group_id]
        variant_id = _find_matching_variant(group, template_text)
        if variant_id is not None:
            variant = group.variants[variant_id]
            group.variants[variant_id] = ReferenceVariant(
                template_path=variant.template_path,
                exact_template_count=variant.exact_template_count + 1,
                exact_records_count=variant.exact_records_count + len(parsed.records),
            )
        else:
            variant_id = str(len(group.variants) + 1)
            group.variants[variant_id] = ReferenceVariant(
                template_path=str(template_path),
                exact_template_count=1,
                exact_records_count=len(parsed.records),
            )
            dest_name = f"{group_id}-template{variant_id}.textfsm"
            (integration_dir / dest_name).write_text(template_text, encoding="utf-8")

    _save_reference(
        integration_dir / "reference.json", reference, total_case_count=len(run_dirs)
    )
    return reference


def _trial_passed(run_dir: Path) -> bool:
    """A trial is only clustering material if its own summary.json says it
    passed. This isn't re-derivable from template.textfsm + sample.txt
    alone: a template can be truncated (generation not ready) yet still
    happen to parse its own sample, which the record-schema re-parse below
    wouldn't catch on its own — unlike total_case_count, "did this specific
    past trial succeed" isn't something that goes stale, so trusting the
    stored verdict here is correct, not a shortcut."""
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return False
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return bool(summary.get("passed"))


def _find_matching_group(reference: Reference, keys: list[str]) -> str | None:
    for group_id, group in reference.items():
        if group.keys == keys:
            return group_id
    return None


def _find_matching_variant(group: ReferenceGroup, template_text: str) -> str | None:
    for variant_id, variant in group.variants.items():
        existing_text = Path(variant.template_path).read_text(encoding="utf-8")
        if existing_text == template_text:
            return variant_id
    return None


def build_reference_summary(store_root: Path) -> dict[str, Any]:
    """Aggregate every reference.json under the integration tier into one
    cross-cli-name match-rate report — a read-only transform of whatever
    build_integration() has already written, no filesystem rescan of
    trials/. Ratios are 0.0 for any cli-name with total_case_count == 0
    (nothing has been integrated for it yet), rather than dividing by zero.
    """
    integration_root = paths.tier_root(store_root, paths.INTEGRATION)
    cases: dict[str, Any] = {}

    if integration_root.exists():
        for reference_path in sorted(integration_root.rglob("reference.json")):
            case_key = reference_path.parent.relative_to(integration_root).as_posix()
            raw = json.loads(reference_path.read_text(encoding="utf-8"))
            total_case_count = raw.get("total_case_count", 0)

            groups_summary = {}
            for group_id, group_raw in raw.get("groups", {}).items():
                group_case_count = group_raw.get("group_case_count", 0)
                variants_summary = {}
                for variant_id, variant_raw in group_raw.get("variants", {}).items():
                    exact = variant_raw.get("exact_template_count", 0)
                    variants_summary[variant_id] = {
                        "ratio_of_group": (
                            exact / group_case_count if group_case_count else 0.0
                        ),
                        "ratio_of_total": (
                            exact / total_case_count if total_case_count else 0.0
                        ),
                    }
                groups_summary[group_id] = {
                    "keys": group_raw.get("keys", []),
                    "case_count": group_case_count,
                    "ratio": (
                        group_case_count / total_case_count if total_case_count else 0.0
                    ),
                    "variants": variants_summary,
                }

            cases[case_key] = {
                "total_case_count": total_case_count,
                "groups": groups_summary,
            }

    return {
        "trial_project": str(paths.tier_root(store_root, paths.TRIALS)),
        "cases": cases,
    }


def write_reference_summary(store_root: Path) -> Path:
    """Write build_reference_summary()'s report to
    integration/reference-summary.json and return its path."""
    summary = build_reference_summary(store_root)
    path = paths.reference_summary_path(store_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return path
