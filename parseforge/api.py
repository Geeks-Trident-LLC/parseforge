"""Public Python API — the single place to import parseforge's stable,
supported surface from. Mirrors textfsm-ai's own api.py convention
(https://github.com/Geeks-Trident-LLC/textfsm-ai): one entry point per
pipeline stage (SPEC.md §5), plus the types each one returns or accepts.

Provider-specific naming builders (``AnthropicRegexBuilder``,
``OCIRegexBuilder``, ...) aren't re-exported here — they're already a
clean, documented import path via :mod:`parseforge.naming` directly, and
listing all eighteen here would bloat this module without adding
anything. Anything not listed in ``__all__`` (module-internal helpers,
provider implementation details, CLI plumbing) isn't part of the public
API and may change without notice.

``naming``'s and ``generation``'s ``TokenUsage`` classes are separate
types that happen to share a name (naming makes one call per cache
miss; generation's is already accumulated across every LLM call in its
own pipeline, see ``GenerationResult.usage``) — aliased here as
``NamingTokenUsage``/``GenerationTokenUsage`` to avoid the collision,
the same convention this package's own test suite already uses.
"""

from __future__ import annotations

from .drift import DriftCheckResult, DriftGate, check_drift
from .generation import GenerationResult, generate
from .generation import TokenUsage as GenerationTokenUsage
from .integration import (
    Reference,
    ReferenceGroup,
    ReferenceVariant,
    build_integration,
    build_reference_summary,
    write_reference_summary,
)
from .naming import (
    CliContext,
    LLMCLIResponse,
    NamingResolution,
    RegexBuilder,
    cli_name,
    resolve_cli_name,
)
from .naming import TokenUsage as NamingTokenUsage
from .paths import DEFAULT_STORE_ROOT, DeviceKey, discover_device_keys
from .pipeline import (
    LLMProviderConfig,
    Mode,
    TrialMetadata,
    TrialResult,
    run_command_pipeline,
)
from .promotion import (
    GroupEvaluation,
    PromotionDecision,
    PromotionGate,
    PromotionMetadata,
    PromotionMode,
    PromotionRunResult,
    UserReviewedRequest,
    decide_promotion,
    evaluate_cases,
    promote_auto,
    promote_user_reviewed,
)
from .sampling import DeviceConnection, Sampler, sample
from .validation import ParseResult, parse

__all__ = [
    # Naming (SPEC.md §2) — resolve a raw CLI command to its canonical
    # cli-name, cached after the first LLM call.
    "cli_name",
    "resolve_cli_name",
    "NamingResolution",
    "CliContext",
    "RegexBuilder",
    "LLMCLIResponse",
    "NamingTokenUsage",
    # Sampling (SPEC.md §3) — capture raw command output from a device.
    "sample",
    "DeviceConnection",
    "Sampler",
    # Generation (SPEC.md §5 steps 5-6) — sample -> candidate TextFSM
    # template, via textfsm-ai's delivery pipeline.
    "generate",
    "GenerationResult",
    "GenerationTokenUsage",
    # Validation (SPEC.md §5 step 7) — self-validate a template against
    # its own sample.
    "parse",
    "ParseResult",
    # Pipeline orchestration (SPEC.md §5) — one call runs steps 1-7
    # (naming -> sampling -> generation -> validation) for a single trial.
    "run_command_pipeline",
    "LLMProviderConfig",
    "TrialMetadata",
    "TrialResult",
    "Mode",
    # Integration (SPEC.md §5 step 8) — cluster trials by output schema.
    "build_integration",
    "build_reference_summary",
    "write_reference_summary",
    "Reference",
    "ReferenceGroup",
    "ReferenceVariant",
    # Promotion (SPEC.md §5 step 9) — auto-promote groups that clear
    # their gate; queue everything else for human review.
    "promote_auto",
    "promote_user_reviewed",
    "decide_promotion",
    "evaluate_cases",
    "PromotionGate",
    "PromotionMetadata",
    "UserReviewedRequest",
    "GroupEvaluation",
    "PromotionRunResult",
    "PromotionDecision",
    "PromotionMode",
    # Drift monitoring (SPEC.md §5 step 11) — check an authoritative
    # template against new production samples.
    "check_drift",
    "DriftGate",
    "DriftCheckResult",
    # Store-root layout helpers.
    "DEFAULT_STORE_ROOT",
    "DeviceKey",
    "discover_device_keys",
]
