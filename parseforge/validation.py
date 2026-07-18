"""Validation — self-validation (SPEC.md §5 step 7) and the parsing
primitive used by integration's group clustering (§3.2, §5 step 8).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import textfsm


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
    step 7) and by :mod:`parseforge.integration` to derive a trial's
    output field-key signature for group clustering (step 8).
    """
    try:
        fsm = textfsm.TextFSM(io.StringIO(template_text))
        rows = fsm.ParseText(input_text)
    except Exception as exc:
        return ParseResult(records=[], errors=[str(exc)])
    records = [dict(zip(fsm.header, row)) for row in rows]
    return ParseResult(records=records, errors=[])
