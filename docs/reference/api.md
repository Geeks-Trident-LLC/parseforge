# API Reference

Everything below is exported from [`parseforge.api`](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/parseforge/api.py)
and re-exported at the package root (`from parseforge import ...`).
Anything not listed here — module-internal helpers, provider
implementation details, CLI plumbing — isn't part of the public API and
may change without notice. See the [Python API guide](../guides/python-api.md)
for worked examples.

## Naming — SPEC.md §2

Resolve a raw CLI command to its canonical, indexed cli-name.

`cli_name(command, context, builder=UnimplementedRegexBuilder(), index_path=DEFAULT_INDEX_PATH, **kwargs) -> str`
: Look up (or resolve and cache) a command's cli-name. `**kwargs` (e.g.
  `max_tokens`) pass through to the builder's underlying API call.

`resolve_cli_name(command, context, builder=..., index_path=..., **kwargs) -> NamingResolution`
: Same as `cli_name()`, but returns the full resolution — including the
  raw LLM response, if any — instead of just the name.

`NamingResolution`
: `name: str`, `response: LLMCLIResponse | None` — `response` is `None`
  on a cache hit, since no LLM call happens at all in that case.

`CliContext`
: `vendor: str`, `family: str`, `os: str`, `version: str` — the device
  context every naming/generation call needs.

`RegexBuilder`
: `Protocol` every naming provider implements —
  `build_pattern(command, context, **kwargs) -> LLMCLIResponse`. See
  [Providers](../guides/providers.md) for the eighteen concrete builder
  classes (`AnthropicRegexBuilder`, `OCIRegexBuilder`, ...), importable
  from `parseforge.naming` — not re-exported at the root.

`LLMCLIResponse`
: `content: str`, `raw: Any`, `usage: NamingTokenUsage`,
  `duration_ms: float`, `reason: str`, `ready: bool` — `ready=False` means
  the response was cut off before completing (e.g. hit `max_tokens`).

`NamingTokenUsage`
: `input_tokens: int`, `output_tokens: int`, `total_tokens: int` — one
  naming LLM call's usage. Aliased from `naming.llm.TokenUsage` to avoid
  colliding with `GenerationTokenUsage` (a separate class with the same
  shape).

## Sampling — SPEC.md §3

Capture raw command output from a device.

`sample(sampler, connection, command) -> str`
: Run `command` over `connection` using `sampler` and return the raw
  output.

`DeviceConnection`
: `host: str`, `username: str`, `password: str`, `device_type: str`
  (e.g. `"cisco_ios"`).

`Sampler`
: `Protocol` a connector backend implements —
  `run_command(connection, command) -> str`. `NetmikoSampler`
  (`parseforge.sampling.backends`, needs the `sampling` extra) is the
  only backend today.

## Generation — SPEC.md §5 steps 5-6

Sample → candidate TextFSM template, via textfsm-ai's delivery pipeline.

`generate(sample, provider, api_key, model, **kwargs) -> GenerationResult`
: Run textfsm-ai's full sample → template → DSL-compiled pipeline.
  Never raises for a failed *generation* (check `.ready`); does raise
  `ImportError` if `provider`'s SDK isn't installed. `**kwargs` forwards
  to textfsm-ai's `run_pipeline()` (`endpoint`, `region`,
  `compartment_id`, `max_tries`, ...).

`GenerationResult`
: `template: str` (canonical, DSL-compiled), `raw_template: str`
  (pre-cleanup, as the LLM returned it), `readable_dsl: str`,
  `recognizers: list[str]`, `records: list[dict[str, str]]`,
  `usage: GenerationTokenUsage`, `duration_ms: float`, `ready: bool`,
  `reason: str`, `raw: dict[str, Any]` (full debug payload, credentials
  redacted).

`GenerationTokenUsage`
: `input_tokens: int`, `output_tokens: int`, `total_tokens: int` —
  already accumulated across every LLM call in the generation pipeline
  (every base-prompt attempt and correction-prompt retry), courtesy of
  textfsm-ai's own `accumulate_usage()`. Aliased from
  `generation.TokenUsage`.

## Validation — SPEC.md §5 step 7

Self-validate a template against its own sample.

`parse(template_text, input_text) -> ParseResult`
: Run `template_text` against `input_text` and report what parsed.

`ParseResult`
: `records: list[dict]`, `errors: list[str]`, and a `passed` property
  (`True` iff `errors` is empty).

## Pipeline orchestration — SPEC.md §5

One call runs steps 1-7 (naming → sampling → generation → validation)
for a single trial, writing the result under a trial directory.

`run_command_pipeline(command, context, connection, naming_builder, sampler, generation_config, *, store_root=DEFAULT_STORE_ROOT, naming_index_path=DEFAULT_INDEX_PATH, metadata=TrialMetadata(), mode=Mode.LOOP) -> TrialResult`
: The full pipeline, one call. Writes `samples/sample.txt`,
  `derive/*.textfsm`/`.txt`, and `summary.json` under
  `<store_root>/trials/<vendor>/<family>/<os>/<cli-name>/<run-id>/`.

`LLMProviderConfig`
: `provider: str`, `api_key: str`, `model: str`, plus provider-specific
  optional fields: `endpoint`/`api_version` (azure), `project`/`location`
  (vertexai), `region` (bedrock/oci), `compartment_id` (oci). Each is
  ignored by every provider it doesn't apply to.

`TrialMetadata`
: `project: str | None`, `username: str | None`, `email: str | None`,
  `description: str | None`, `note: str | None` — optional context
  recorded in `summary.json`, never used for path resolution.

`TrialResult`
: `run_dir: Path`, `cli_name: str`, `passed: bool`, `duration_ms: int`,
  `total_usage: dict[str, int]` (`input_tokens`/`output_tokens`/
  `total_tokens`, naming + generation combined).

`Mode`
: `LOOP` (sample → generate, per command — the only mode implemented)
  or `BATCH` (collect N samples per command before generating — designed
  in SPEC.md §4, not built).

## Integration — SPEC.md §5 step 8

Cluster every passed trial for a cli-name by output schema.

`build_integration(store_root, key) -> Reference`
: Rebuild `integration/<...>/reference.json` for one `DeviceKey` from
  every trial currently under `trials/`.

`build_reference_summary(store_root) -> dict[str, Any]`
: Aggregate every `reference.json` into one cross-cli-name match-rate
  report — a read-only transform, no filesystem rescan of `trials/`.

`write_reference_summary(store_root) -> Path`
: `build_reference_summary()`, written to
  `integration/reference-summary.json`; returns the path written.

`Reference`
: `dict[str, ReferenceGroup]` — a cli-name's clustered output-schema
  groups.

`ReferenceGroup`
: `keys: list[str]`, `sample_path: str`,
  `variants: dict[str, ReferenceVariant]`.

`ReferenceVariant`
: `template_path: str`, `exact_template_count: int`,
  `exact_records_count: int`.

## Promotion — SPEC.md §5 step 9

Auto-promote every group that clears its gate; queue everything else
for human review.

`promote_auto(store_root, metadata, default_gate=PromotionGate(), case_gates=None) -> PromotionRunResult`
: Refreshes integration first, then promotes every group across every
  case that clears `default_gate` (or its per-case override in
  `case_gates`) into `authoritative/`.

`promote_user_reviewed(store_root, metadata, requests, default_gate=PromotionGate(), case_gates=None) -> PromotionRunResult`
: Same, but only for the specific `(case_key, suffix)` pairs in
  `requests` — a human-reviewed promotion, recorded as a named snapshot
  alongside whatever's currently live rather than overwriting it.

`decide_promotion(match_rate, sample_count, gate) -> PromotionDecision`
: Pure decision: `AUTO_PROMOTED` if both thresholds in `gate` are met,
  else `QUEUED_FOR_REVIEW`.

`evaluate_cases(references, summary, default_gate, case_gates=None, only_cases=None) -> list[GroupEvaluation]`
: Pure decision pass over every group in `references` — no I/O. One
  `decide_promotion()` call per group, per case.

`PromotionGate`
: `match_rate_threshold: float = 1.0`, `min_sample_count: int = 1`.

`PromotionMetadata`
: `user: str`, `email: str | None`, `description: str | None`,
  `note: str | None` — recorded into every `artifact.json`/
  `authoritative-log.json` entry a promotion run writes.

`UserReviewedRequest`
: `case_key: str`, `suffix: str | None`, `gate: PromotionGate | None` —
  one human-reviewed case, tagged with a minor revision marker (e.g.
  `"2"`, `"beta"`) combined with the group's own major version tag.

`GroupEvaluation`
: `case_key: str`, `group_id: str`, `decision: PromotionDecision`,
  `match_rate: float`, `sample_count: int`.

`PromotionRunResult`
: `promoted: list[Path]`, `unqualified: list[GroupEvaluation]`,
  `unmatched_cases: list[str]`, `invalid_requests: list[str]`
  (`USER_REVIEWED` requests with no usable suffix).

`PromotionDecision`
: `AUTO_PROMOTED` or `QUEUED_FOR_REVIEW`.

`PromotionMode`
: `AUTO_PROMOTED` or `USER_REVIEWED`.

## Drift monitoring — SPEC.md §5 step 11

Check an authoritative template against new production samples.

`check_drift(store_root, key, sample_text, *, suffix=None, gate=DriftGate()) -> DriftCheckResult`
: Run the authoritative template for `(key, suffix)` against
  `sample_text`, append the result to that cli-name's `drift-log.json`,
  and return the rolling match rate + status.

`DriftGate`
: `match_rate_threshold: float = 1.0`, `window: int = 20`.

`DriftCheckResult`
: `case_key: str`, `suffix: str | None`, `passed: bool`,
  `match_rate: float`, `status: str` (`"ok"` or `"drifting"`),
  `checked_at: str`, `requeued_to: str | None`.

## Store-root layout helpers

`DEFAULT_STORE_ROOT`
: `Path` — `~/.parseforge/tests`, the default root every workflow
  command reads/writes under.

`DeviceKey`
: `vendor: str`, `family: str`, `os: str`, `cli_name: str` — identifies
  a template family within a store root.

`discover_device_keys(store_root) -> list[DeviceKey]`
: Every `DeviceKey` that has at least one trial on disk under
  `store_root`.
