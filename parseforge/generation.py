"""Generation stage — LLM call and template extraction (SPEC.md §5 steps 5-6).

Writes raw-llm-response.txt / usage.txt (step 5), then extracts and
cleans the template into raw-template / template.textfsm (step 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GenerationResult:
    raw_response: str
    usage: str
    raw_template: str
    template: str


class Generator(Protocol):
    """An LLM backend capable of producing a TextFSM template from sample input.

    ``prior_context`` carries additional samples of the same command when
    running in Mode 1 (batch) per §4.
    """

    def generate(
        self, input_text: str, prior_context: list[str] | None = None
    ) -> GenerationResult: ...


def extract_template(raw_response: str) -> str:
    """Pull the template body out of a raw LLM response (step 6, pre-cleanup)."""
    raise NotImplementedError("extraction rule TBD — see SPEC.md §5 step 6")


def clean_template(raw_template: str) -> str:
    """Normalize an extracted template into a valid template.textfsm body."""
    raise NotImplementedError("cleanup rule TBD — see SPEC.md §5 step 6")
