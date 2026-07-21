"""Authoritative promotion and drift monitoring (SPEC.md §3.3, §5 steps 9-10).

Two entry points, mirroring integration.py's whole-project shape
(build_integration() per case, build_reference_summary() across every
case): :func:`promote_auto` walks every case in the project and promotes
every group that clears its gate. :func:`promote_user_reviewed` is scoped
to a caller-supplied list of ``(case, suffix)`` for promotions a human
has already reviewed, writing suffixed files alongside the unsuffixed
current ones rather than replacing them.

``authoritative/<vendor>/<family>/<os>/<cli-name>/`` is flat — final,
delivery-ready content only, no per-group subdirectory. Every
simultaneously-valid variant for a cli-name (hardware/firmware variance,
§6) is distinguished by filename instead: the first group discovered for
a case (``group1``) owns the unsuffixed "current version" names
(``template.textfsm``, ``recognizers.txt``, ``data/sample.txt``); each
additional group owns ``template-v2.textfsm``, ``template-v3.textfsm``,
etc. — a stable, permanent tag derived from the group's own id, never
renumbered as other groups gain or lose their gate. A USER_REVIEWED
promotion layers the caller's own minor suffix onto that same major tag
(``template-v2-<suffix>.textfsm``), so it never collides with — or
silently overwrites — whichever file currently represents that group's
auto-promoted version. ``golden.hash`` and ``artifact.json`` are the one
exception to per-variant filenames — see below.

Both still gate on the same primitive (:class:`PromotionGate` /
:func:`decide_promotion` — match-rate threshold + minimum sample count),
now evaluated per group using each group's ``ratio_of_passed`` from
:func:`parseforge.integration.build_reference_summary` (a group's share
of only the trials that actually passed — not diluted by raw generation
failures).

Both refresh integration first: :func:`paths.discover_device_keys`
finds every cli-name with a trials/ directory, and
:func:`parseforge.integration.build_integration` reruns for each before
any gate is evaluated. ``reference.json``/``reference-summary.json`` are
snapshots from whenever integration last ran; evaluating a gate against a
stale snapshot would contradict promotion being high-stakes enough to
need current numbers. This costs nothing but filesystem I/O — no LLM
calls happen during integration.

Per cli-name, two complementary artifacts, both singular and unsuffixed
regardless of which group/variant/suffix wrote them: ``golden.hash``
(sha256 of whichever template was most recently promoted, the baseline
future drift checks compare against) and ``artifact.json`` (a snapshot of
that most recent promotion — who/when/mode/match rate/source).
``authoritative-log.json`` is one project-wide append-only history across
every promotion event ever (each entry records its own case/group/suffix),
and ``authoritative-summary.json`` is a project-wide snapshot of the most
recent run — overwritten every call, not accumulated.

A USER_REVIEWED request with no usable suffix (missing or blank) is never
written — that would collide with (or silently pass as) an auto-promoted
"current version" file. Such requests are reported in
``PromotionRunResult.invalid_requests`` instead of being promoted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from parseforge import integration, paths, validation
from parseforge.integration import Reference, ReferenceGroup, ReferenceVariant


class PromotionDecision(str, Enum):
    AUTO_PROMOTED = "auto_promoted"
    QUEUED_FOR_REVIEW = "queued_for_review"


class PromotionMode(str, Enum):
    AUTO_PROMOTED = "auto_promoted"
    USER_REVIEWED = "user_reviewed"


@dataclass(frozen=True)
class PromotionGate:
    """Confidence threshold gating auto-promotion vs. human review (§3.3, §7).

    Left configurable per-project rather than hardcoded — see the open
    question in SPEC.md §7.
    """

    match_rate_threshold: float = 1.0
    min_sample_count: int = 1


@dataclass(frozen=True)
class PromotionMetadata:
    """Who/why for a promotion run, recorded into every artifact.json and
    authoritative-log.json entry written by that run."""

    user: str
    email: str | None = None
    description: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class UserReviewedRequest:
    """One case a human has already reviewed and wants promoted, tagged
    with a caller-supplied minor revision marker (e.g. "2", "beta") —
    parseforge combines it with the group's own major version tag
    (v1, v2, ...) rather than using it as the whole suffix, so it can
    never collide with another group's auto-promoted identity. A missing
    or blank suffix is never promoted — see PromotionRunResult.invalid_requests."""

    case_key: str
    suffix: str | None = None
    gate: PromotionGate | None = None


@dataclass(frozen=True)
class GroupEvaluation:
    case_key: str
    group_id: str
    decision: PromotionDecision
    match_rate: float
    sample_count: int


@dataclass(frozen=True)
class PromotionRunResult:
    promoted: list[Path]  # template files actually written this run
    unqualified: list[GroupEvaluation]
    unmatched_cases: list[str]
    invalid_requests: list[str]  # USER_REVIEWED requests with no usable suffix


def decide_promotion(
    match_rate: float, sample_count: int, gate: PromotionGate
) -> PromotionDecision:
    if (
        sample_count >= gate.min_sample_count
        and match_rate >= gate.match_rate_threshold
    ):
        return PromotionDecision.AUTO_PROMOTED
    return PromotionDecision.QUEUED_FOR_REVIEW


def evaluate_cases(
    references: dict[str, Reference],
    summary: dict[str, Any],
    default_gate: PromotionGate,
    case_gates: dict[str, PromotionGate] | None = None,
    only_cases: set[str] | None = None,
) -> list[GroupEvaluation]:
    """Pure decision pass — no I/O. One decide_promotion() call per group,
    per case, using that group's ratio_of_passed from ``summary`` (see
    :func:`parseforge.integration.build_reference_summary`)."""
    case_gates = case_gates or {}
    cases_summary = summary.get("cases", {})
    results: list[GroupEvaluation] = []

    for case_key, reference in references.items():
        if only_cases is not None and case_key not in only_cases:
            continue
        gate = case_gates.get(case_key, default_gate)
        groups_summary = cases_summary.get(case_key, {}).get("groups", {})

        for group_id in reference:
            group_summary = groups_summary.get(group_id, {})
            match_rate = group_summary.get("ratio_of_passed", 0.0)
            sample_count = group_summary.get("case_count", 0)
            decision = decide_promotion(match_rate, sample_count, gate)
            results.append(
                GroupEvaluation(
                    case_key=case_key,
                    group_id=group_id,
                    decision=decision,
                    match_rate=match_rate,
                    sample_count=sample_count,
                )
            )
    return results


def _representative_variant_id(group_variants: dict[str, ReferenceVariant]) -> str:
    """Pick the variant with the highest exact_template_count, ties broken
    by lowest variant id for determinism."""
    return min(
        group_variants,
        key=lambda vid: (-group_variants[vid].exact_template_count, int(vid)),
    )


def _group_ordinal(group_id: str) -> int:
    return int(group_id.removeprefix("group"))


def _auto_suffix(group_id: str) -> str | None:
    """group1 is the primary/unsuffixed variant; group2, group3, ... get
    template-v2.textfsm, template-v3.textfsm, etc. Stable and permanent —
    derived purely from the group's own id, never renumbered based on
    which groups currently qualify."""
    n = _group_ordinal(group_id)
    return None if n == 1 else f"v{n}"


def _version_tag(group_id: str) -> str:
    """Always-present major version tag (v1, v2, ...) — combined with a
    USER_REVIEWED request's own minor suffix so a reviewed promotion never
    collides with (or silently overwrites) the file that currently
    represents this group's auto-promoted version."""
    return f"v{_group_ordinal(group_id)}"


def _write_promoted_version(
    store_root: Path,
    key: paths.DeviceKey,
    group_id: str,
    reference_group: ReferenceGroup,
    metadata: PromotionMetadata,
    evaluation: GroupEvaluation,
    mode: PromotionMode,
    *,
    suffix: str | None,
) -> Path:
    """Copy the group's representative variant into the flat
    authoritative/<cli-name>/ directory, write its data/ (sample + parsed
    records), and (re)write golden.hash, artifact.json (both singular,
    unsuffixed — always the most recent promotion for this cli-name), and
    append to authoritative-log.json. ``suffix=None`` writes the unsuffixed
    "current version" filenames for template/recognizers/data; a suffix
    writes those alongside them without replacing them. Returns the
    template file path written."""
    variant_id = _representative_variant_id(reference_group.variants)
    variant = reference_group.variants[variant_id]

    source_template = Path(variant.template_path)
    source_sample = Path(reference_group.sample_path)
    source_recognizers = source_template.parent / "recognizers.txt"

    template_text = source_template.read_text(encoding="utf-8")
    sample_text = source_sample.read_text(encoding="utf-8")
    suffix_part = f"-{suffix}" if suffix else ""

    dest_dir = paths.authoritative_dir(store_root, key)
    dest_dir.mkdir(parents=True, exist_ok=True)
    data_dir = paths.promoted_data_dir(store_root, key)
    data_dir.mkdir(parents=True, exist_ok=True)

    template_dest = dest_dir / f"template{suffix_part}.textfsm"
    template_dest.write_text(template_text, encoding="utf-8")

    if source_recognizers.exists():
        (dest_dir / f"recognizers{suffix_part}.txt").write_text(
            source_recognizers.read_text(encoding="utf-8"), encoding="utf-8"
        )

    (data_dir / f"sample{suffix_part}.txt").write_text(sample_text, encoding="utf-8")
    parsed = validation.parse(template_text, sample_text)
    (data_dir / f"records{suffix_part}.json").write_text(
        json.dumps(parsed.records, indent=2), encoding="utf-8"
    )

    # golden.hash and artifact.json are singular, unsuffixed -- always
    # reflect the most recent promotion for this cli-name, regardless of
    # which group/variant/suffix triggered it.
    golden_hash = hashlib.sha256(template_dest.read_bytes()).hexdigest()
    paths.golden_hash_path(store_root, key).write_text(golden_hash, encoding="utf-8")

    artifact = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": metadata.user,
        "email": metadata.email,
        "description": metadata.description,
        "note": metadata.note,
        "mode": mode.value,
        "suffix": suffix,
        "case": evaluation.case_key,
        "group_id": group_id,
        "source_template": str(source_template),
        "match_rate": evaluation.match_rate,
        "sample_count": evaluation.sample_count,
    }
    paths.artifact_path(store_root, key).write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    log_path = paths.authoritative_log_path(store_root)
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    log.append(
        {
            "case": evaluation.case_key,
            "group_id": group_id,
            "mode": mode.value,
            "suffix": suffix,
            "match_rate": evaluation.match_rate,
            "sample_count": evaluation.sample_count,
            "template_source": str(source_template),
            "created_by": metadata.user,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")

    return template_dest


def _refresh_and_summarize(
    store_root: Path,
) -> tuple[dict[str, paths.DeviceKey], dict[str, Reference], dict[str, Any]]:
    """Rebuild integration for every cli-name currently under trials/, then
    summarize — the "always fresh" step both promote_* entry points share."""
    keys_by_case: dict[str, paths.DeviceKey] = {}
    references: dict[str, Reference] = {}
    for key in paths.discover_device_keys(store_root):
        case_key = key.relative_path().as_posix()
        keys_by_case[case_key] = key
        references[case_key] = integration.build_integration(store_root, key)
    summary = integration.build_reference_summary(store_root)
    return keys_by_case, references, summary


def _write_authoritative_summary(
    store_root: Path, mode: PromotionMode, result: PromotionRunResult
) -> Path:
    summary = {
        "project": str(store_root),
        "mode": mode.value,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "promoted": [str(p) for p in result.promoted],
        "unqualified": [
            {
                "case": e.case_key,
                "group_id": e.group_id,
                "match_rate": e.match_rate,
                "sample_count": e.sample_count,
            }
            for e in result.unqualified
        ],
        "unmatched_cases": result.unmatched_cases,
        "invalid_requests": result.invalid_requests,
    }
    path = paths.authoritative_summary_path(store_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _promote_qualifying(
    store_root: Path,
    metadata: PromotionMetadata,
    mode: PromotionMode,
    evaluations: list[GroupEvaluation],
    keys_by_case: dict[str, paths.DeviceKey],
    references: dict[str, Reference],
    suffix_resolver: Callable[[str, str], str | None],
) -> tuple[list[Path], list[GroupEvaluation]]:
    promoted: list[Path] = []
    unqualified: list[GroupEvaluation] = []
    for evaluation in evaluations:
        if evaluation.decision is not PromotionDecision.AUTO_PROMOTED:
            unqualified.append(evaluation)
            continue
        key = keys_by_case[evaluation.case_key]
        reference_group = references[evaluation.case_key][evaluation.group_id]
        dest = _write_promoted_version(
            store_root,
            key,
            evaluation.group_id,
            reference_group,
            metadata,
            evaluation,
            mode,
            suffix=suffix_resolver(evaluation.case_key, evaluation.group_id),
        )
        promoted.append(dest)
    return promoted, unqualified


def promote_auto(
    store_root: Path,
    metadata: PromotionMetadata,
    default_gate: PromotionGate = PromotionGate(),
    case_gates: dict[str, PromotionGate] | None = None,
) -> PromotionRunResult:
    """Walk every case in the project; promote every group that clears its
    gate — group1 unsuffixed, group2/group3/... as template-v2/v3/...;
    write authoritative-summary.json."""
    keys_by_case, references, summary = _refresh_and_summarize(store_root)
    evaluations = evaluate_cases(references, summary, default_gate, case_gates)

    promoted, unqualified = _promote_qualifying(
        store_root,
        metadata,
        PromotionMode.AUTO_PROMOTED,
        evaluations,
        keys_by_case,
        references,
        suffix_resolver=lambda _case_key, group_id: _auto_suffix(group_id),
    )

    result = PromotionRunResult(
        promoted=promoted,
        unqualified=unqualified,
        unmatched_cases=[],
        invalid_requests=[],
    )
    _write_authoritative_summary(store_root, PromotionMode.AUTO_PROMOTED, result)
    return result


def promote_user_reviewed(
    store_root: Path,
    metadata: PromotionMetadata,
    requests: list[UserReviewedRequest],
    default_gate: PromotionGate = PromotionGate(),
) -> PromotionRunResult:
    """Same refresh as promote_auto, but scoped to requested cases; a
    case_key with no matching trials at all is reported in
    unmatched_cases instead of being evaluated, and a request with no
    usable suffix is reported in invalid_requests instead of being
    written — a blank/missing suffix would collide with (or silently pass
    as) an auto-promoted "current version" file. Each qualifying group in
    a requested case is promoted under "v<group's major>-<request's
    minor>" (e.g. "v2-3"), alongside whatever that group's current
    auto-promoted files already are."""
    keys_by_case, references, summary = _refresh_and_summarize(store_root)

    unmatched_cases = [r.case_key for r in requests if r.case_key not in references]
    candidate_requests = {r.case_key: r for r in requests if r.case_key in references}

    invalid_requests = [
        case_key
        for case_key, request in candidate_requests.items()
        if not request.suffix or not request.suffix.strip()
    ]
    matched_requests = {
        case_key: request
        for case_key, request in candidate_requests.items()
        if case_key not in invalid_requests
    }

    case_gates = {
        case_key: request.gate
        for case_key, request in matched_requests.items()
        if request.gate is not None
    }
    evaluations = evaluate_cases(
        references,
        summary,
        default_gate,
        case_gates,
        only_cases=set(matched_requests),
    )

    def _resolve_suffix(case_key: str, group_id: str) -> str:
        minor = matched_requests[case_key].suffix
        return f"{_version_tag(group_id)}-{minor}"

    promoted, unqualified = _promote_qualifying(
        store_root,
        metadata,
        PromotionMode.USER_REVIEWED,
        evaluations,
        keys_by_case,
        references,
        suffix_resolver=_resolve_suffix,
    )

    result = PromotionRunResult(
        promoted=promoted,
        unqualified=unqualified,
        unmatched_cases=unmatched_cases,
        invalid_requests=invalid_requests,
    )
    _write_authoritative_summary(store_root, PromotionMode.USER_REVIEWED, result)
    return result


@dataclass(frozen=True)
class DriftStatus:
    match_rate: float
    status: str  # "ok" | "drifting" | "superseded" — see SPEC.md §6

    def breached(self, threshold: float) -> bool:
        return self.match_rate < threshold
