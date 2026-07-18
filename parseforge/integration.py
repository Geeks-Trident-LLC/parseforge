"""Integration — cluster trials for a cli-name into output-schema groups
(SPEC.md §3.2, §5 step 8; §6 multi-variant note).

Unlike §3.2's original single "common-result" winner, a cli-name's output
can legitimately vary by hardware/firmware (§6). ``build_integration``
groups every trial for a cli-name by the field-key signature of its parsed
records, and within a group further distinguishes byte-identical template
variants from divergent ones. This is pure evidence gathering — no
promotion decision is made or stored here (see :mod:`parseforge.promotion`
for that, which reads ``reference.json`` back out).

``build_integration`` is a full rebuild each call: every trial run-dir for
the cli-name is rescanned and ``reference.json`` is regenerated from
scratch, rather than incrementally diffed against its prior contents. A new
trial is only ever compared against the (small) set of distinct groups
already found, not every past trial, so this costs the same either way and
avoids partial-state bugs. Group/variant numbering stays deterministic
because trial run-dirs are iterated in chronological run-id order.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

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


Reference = dict[str, ReferenceGroup]


def _load_reference(path: Path) -> Reference:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    reference: Reference = {}
    for group_id, group_raw in raw.items():
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


def _save_reference(path: Path, reference: Reference) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {group_id: asdict(group) for group_id, group in reference.items()}
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
        _save_reference(integration_dir / "reference.json", reference)
        return reference

    run_dirs = sorted(d for d in trials_dir.iterdir() if d.is_dir())

    for run_dir in run_dirs:
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
            dest_name = f"template{variant_id}-{group_id}.textfsm"
            (integration_dir / dest_name).write_text(template_text, encoding="utf-8")

    _save_reference(integration_dir / "reference.json", reference)
    return reference


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
