"""Pipeline orchestration (SPEC.md §4, §5).

Mode 2 (loop: sample -> generate, per command) is the MVP per §4's
recommendation. Mode 1 (batch: gather-then-generate) is a config flag
that only changes the sampling stage — generation, storage, and
validation stay identical between modes.
"""

from __future__ import annotations

from enum import Enum

from parseforge import naming, paths


class Mode(str, Enum):
    LOOP = "loop"  # MVP: sample -> generate, per command (§4)
    BATCH = "batch"  # collect N samples per command before generation (§4)


def run_command_pipeline(
    command: str,
    key_fields: dict,
    regex_builder: naming.RegexBuilder = naming.UnimplementedRegexBuilder(),
    mode: Mode = Mode.LOOP,
) -> None:
    """Execute steps 1-7 of the pipeline for a single CLI command.

    1. Input intake is the caller's responsibility (device info, auth,
       command list, mode selection already resolved into ``key_fields``,
       which must supply vendor/family/os/version).
    2. Name generation — :func:`parseforge.naming.cli_name` (LLM-backed,
       cached — see :mod:`parseforge.naming`).
    3. Path resolution — :mod:`parseforge.paths`.
    4. Sampling — :mod:`parseforge.sampling`.
    5-6. Generation — :mod:`parseforge.generation`.
    7. Self-validation — :mod:`parseforge.validation`.

    Steps 8-11 (integration selection, authoritative promotion, drift
    monitoring, repeat/loop) run out-of-band across all trials for a
    cli-name, not per single pipeline invocation — see
    :mod:`parseforge.validation` and :mod:`parseforge.promotion`.
    """
    context = naming.CliContext(**key_fields)
    name = naming.cli_name(command, context, builder=regex_builder)
    key = paths.DeviceKey(cli_name=name, **key_fields)
    raise NotImplementedError(
        f"wire sampling -> generation -> validation for {key!r} (mode={mode.value})"
    )
