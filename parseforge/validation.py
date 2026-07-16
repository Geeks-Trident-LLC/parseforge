"""Validation — self-validation (SPEC.md §5 step 7) and cross-validation
for integration selection (§3.2, §5 step 8).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParseResult:
    records: list[dict]
    errors: list[str]

    @property
    def passed(self) -> bool:
        return not self.errors


def parse(template_text: str, input_text: str) -> ParseResult:
    """Run a template.textfsm against an input.txt sample.

    Used both for self-validation (a template against its own sample,
    step 7) and cross-validation (every candidate against every known
    sample for a cli-name, step 8).
    """
    raise NotImplementedError("wrap textfsm.TextFSM — see SPEC.md §5 steps 7-8")


@dataclass(frozen=True)
class CandidateScore:
    run_id: str
    match_rate: float
    failed_samples: list[str]


def select_common_result(
    candidates: dict[str, str], samples: dict[str, str]
) -> CandidateScore:
    """Cross-validate every candidate template against every known sample.

    ``candidates`` maps trial run_id -> template.textfsm text.
    ``samples`` maps sample id -> input.txt text.

    Promotes whichever template parses the largest share of *all* known
    samples correctly (not just the sample it was generated from) — an
    overfit template that only matches its own source sample must lose
    to a template that generalizes, per §3.2.
    """
    raise NotImplementedError("scoring/selection rule — see SPEC.md §3.2")
