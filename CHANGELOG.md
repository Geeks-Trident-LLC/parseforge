## v0.2.12 — 2026-08-02

### Added
- `BedrockRegexBuilder` (`parseforge[bedrock]`) — the seventeenth naming
  provider. Like Vertex AI, Bedrock has no API key at all — it
  authenticates via AWS's own credential chain — and needs only a
  `region`. Talks to `boto3`'s bedrock-runtime Converse API directly;
  unlike Mistral/Cohere/Azure/Gemini/Vertex AI's single status-coded
  error class, Bedrock raises a family of named `ClientError`
  subclasses, classified by class name — the same approach already used
  for Anthropic/OpenAI's own named-exception families
- `OCIRegexBuilder` (`parseforge[oci]`) — the eighteenth naming
  provider, and the most complex auth shape yet: no API key at all
  (Oracle Cloud signs each request cryptographically against local
  `~/.oci/config` credentials), plus *two* app-specific parameters —
  `region` and `compartment_id` (the OCID of the compartment/tenancy to
  bill and scope requests to). Talks to the native `oci` SDK's
  `GenerativeAiInferenceClient.chat()` Generic chat format directly
  (OpenAI-shaped messages/choices, the format shared by Meta Llama and
  xAI Grok models on OCI); errors are a single `ServiceError` class
  classified by its HTTP-style `.status` code, same approach as
  Mistral/Cohere/Azure/Gemini
- `NO_API_KEY_PROVIDERS` gains `bedrock`/`oci`. New `--region`/
  `--compartment-id` options (and `--naming-region`/
  `--naming-compartment-id` on `run`) across `name`, `run`, `check
  --provider`, `generate-template`, and `trial.yaml`/
  `generate-template.yaml` config files
- `pipeline.py`'s `LLMProviderConfig` gains `region`/`compartment_id`
  fields. `region` is shared across vertexai/bedrock/oci (only one is
  ever set for a given trial, since a trial has exactly one generation
  provider); `compartment_id` is oci-only and has its own dedicated
  kwarg on `run_pipeline()`, needing no such sharing

### Fixed
- A new `test_oci.py` unit test file was missing `from __future__
  import annotations`, which broke collection on Python 3.9 (`str |
  None` union syntax needs the future import before Python 3.10) —
  caught by CI before merge, not shipped

## v0.2.11 — 2026-08-02

### Added
- `VertexAIRegexBuilder` (`parseforge[vertexai]`) — the sixteenth
  naming provider, and the first after Azure to break the usual
  `api_key`+`model` shape. Vertex AI has no API key at all — it
  authenticates via GCP's own Application Default Credentials — and
  needs a `project`/`location` pair instead. Reuses the `google-genai`
  SDK already installed for Gemini (`Client(vertexai=True, project=,
  location=)` vs. Gemini's own `Client(api_key=)`), serving the
  identical Gemini model catalog under GCP's separate enterprise
  billing
- New `NO_API_KEY_PROVIDERS` set (`cli/config.py`) — providers that
  authenticate without any API key at all; `--api-key`/`api_key` is now
  required conditionally on provider instead of unconditionally
- New `--gcp-project`/`--gcp-location` CLI flags — prefixed `gcp-`
  specifically to avoid colliding with `run`'s pre-existing free-text
  `--project` trial-label flag — across `name`, `run` (both naming and
  generation sides), `check --provider`, and `generate-template`;
  `trial.yaml`/`generate-template.yaml` config files gain matching
  `project`/`location` keys
- `pipeline.py`'s `LLMProviderConfig` gains `project`/`location`
  fields, mapped onto `generation.generate()`'s `region=` kwarg — the
  name `run_pipeline()` itself expects, not `location`

## v0.2.10 — 2026-08-02

### Added
- `GeminiRegexBuilder` (`parseforge[gemini]`) — the fifteenth naming
  provider. Like Mistral/Cohere/Azure, Google's official Python SDK
  (`google-genai`) isn't built on the OpenAI client library; it has its
  own client shape (`client.models.generate_content()`), talked to
  directly. Error classification is status-code-based (`exc.code` on the
  single `APIError` class the SDK raises for every HTTP failure), same
  approach as Mistral/Cohere/Azure. Two Gemini-specific wrinkles:
  `finish_reason` is a str-subclassed enum whose own `__str__` prints
  `"FinishReason.STOP"` rather than `"STOP"` (`.value` is used instead),
  and thinking mode is explicitly disabled by default
  (`thinking_budget=0`, overridable via a `thinking_budget` kwarg),
  matching textfsm-ai's own `GeminiProvider` default
- `models.yaml` gained a `gemini` entry (default `gemini-2.5-flash`,
  matching textfsm-ai's `model_catalog` default) plus 6 other supported
  models from textfsm-ai's `pricing.yaml`
- New `pyproject.toml` `gemini` extra (`google-genai>=0.2.0` +
  `textfsm-ai[gemini]>=0.6.1`). Also added to `dev` so gemini's tests
  never silently skip
- `--api-key`/`--provider` help text (CLI) and the provider extras list
  (README) now enumerate all fifteen providers

## v0.2.9 — 2026-08-02

### Added
- `AzureRegexBuilder` (`parseforge[azure]`) — the fourteenth naming
  provider, and the first that doesn't fit the `api_key`+`model` shape
  every prior provider used. Azure OpenAI has no fixed `base_url` or
  model catalog: `endpoint` is the caller's own Azure resource, and the
  usual "model" concept is replaced by an account-specific `deployment`
  name (`AZURE_API_KEY`/`AZURE_ENDPOINT`/`AZURE_API_VERSION`/
  `AZURE_DEPLOYMENT`). Talks to the `azure-ai-inference` SDK's
  `ChatCompletionsClient` directly; error classification is
  status-code-based (`exc.status_code` on the single `HttpResponseError`
  class the SDK raises for every HTTP failure), same approach as
  Mistral/Cohere
- New `--endpoint`/`--api-version`/`--deployment` options on `name`,
  `check --provider`, and `generate-template`; `run` gets both
  `--naming-endpoint`/`--naming-api-version`/`--naming-deployment`
  (naming side) and `--endpoint`/`--api-version`/`--deployment`
  (generation side); `trial.yaml`/`generate-template.yaml` config files
  gain matching `endpoint`/`api_version`/`deployment` keys
- New pyproject.toml `azure` extra (`azure-ai-inference>=1.0.0b9`,
  matching textfsm-ai's own floor). Also added to `dev` so azure's
  tests never silently skip

### Fixed
- `_build_regex_builder()` would have raised a plain `TypeError` for any
  azure trial/config, since `TrialConfig.model` is always present but
  `AzureRegexBuilder` has no `model` parameter at all — deployment now
  takes precedence and `model` is simply not forwarded when it's set
- The generation-side `api_version` had no default anywhere unlike
  naming's builder, which would have silently sent an empty string to a
  real Azure API call — the same default is now applied at the
  `pipeline.py`/`generate-template` call sites

## v0.2.8 — 2026-08-02

### Added
- Two new naming providers, both using their vendor's *native* SDK rather
  than the `openai`-compat shape every prior provider used — the first
  providers in this project that aren't OpenAI-compatible:
  - `MistralRegexBuilder` (`parseforge[mistral]`, `MISTRAL_API_KEY`,
    default `mistral-small-latest`) — talks to the native `mistralai` SDK's
    `client.chat.complete()`. The SDK raises a single `SDKError` for every
    HTTP failure (status on `exc.raw_response.status_code`) rather than a
    family of named exception classes, so retryability is classified by
    status code instead of reusing `providers/errors.py`'s
    class-name-based classification. Pinned to `mistralai==1.10.0` (the
    last release supporting Python 3.9, matching textfsm-ai's own pin)
  - `CohereRegexBuilder` (`parseforge[cohere]`, `COHERE_API_KEY`, default
    `command-light`) — talks to the native `cohere` SDK's synchronous
    `ClientV2.chat()`. Cohere raises a family of named exceptions
    (`BadRequestError`, `UnauthorizedError`, ...) whose names don't line
    up with OpenAI/Anthropic's, but all carry `exc.status_code`, so
    retryability is likewise classified by status code. Response content
    is a list of text/thinking blocks rather than a plain string, and
    `usage.tokens` has no `total_tokens` field at all (computed locally).
    Pinned to `cohere==5.21.1` for the same Python 3.9 reason
- `dev` extra now also pulls in `mistralai==1.10.0` and `cohere==5.21.1`
  directly, alongside the existing `anthropic`/`openai`, so both providers'
  tests always run rather than silently skipping
- `--api-key`/`--provider` help text (CLI) and the provider extras list
  (README) now enumerate all thirteen providers

## v0.2.6 — 2026-08-02

### Added
- Eight new naming providers, each with a lazily-imported `openai`-SDK-backed
  `RegexBuilder`, an optional `pyproject.toml` extra, a `models.yaml` entry,
  live-API test coverage (`tests/real/naming/`, `tests/real/generation/`), and
  unit tests (`tests/unit/naming/providers/`) — all wired automatically into
  every `--provider`/`--naming-provider` CLI surface via the shared
  `_BUILDERS` registry:
  - `GroqRegexBuilder` (`parseforge[groq]`, `GROQ_API_KEY`,
    default `llama-3.1-8b-instant`)
  - `XAIRegexBuilder` (`parseforge[xai]`, `XAI_API_KEY`,
    default `grok-3-mini`)
  - `TogetherRegexBuilder` (`parseforge[together]`, `TOGETHER_API_KEY`,
    default `meta-llama/Llama-3.1-8B-Instruct-Turbo`)
  - `FireworksRegexBuilder` (`parseforge[fireworks]`, `FIREWORKS_API_KEY`,
    default `accounts/fireworks/models/llama-v3p1-8b-instruct`)
  - `PerplexityRegexBuilder` (`parseforge[perplexity]`, `PERPLEXITY_API_KEY`,
    default `sonar`)
  - `OpenRouterRegexBuilder` (`parseforge[openrouter]`, `OPENROUTER_API_KEY`,
    default `google/gemini-2.5-flash-lite`) — a model aggregator/router that
    re-exposes many upstream providers under a `vendor/model` namespace
  - `MoonshotRegexBuilder` (`parseforge[moonshot]`, `MOONSHOT_API_KEY`,
    default `moonshot-v1-8k`) — uses the global `api.moonshot.ai` endpoint
  - `CerebrasRegexBuilder` (`parseforge[cerebras]`, `CEREBRAS_API_KEY`,
    default `llama3.1-8b`)
- `dev` extra unchanged (still just `anthropic`/`openai` directly) — the new
  providers all reuse the `openai` SDK against a different `base_url`, so no
  new SDK dependency was needed for tests to exercise them
- `--api-key`/`--provider` help text (CLI) and the provider extras list
  (README) now enumerate all eleven providers

## v0.2.5 — 2026-08-02

### Added
- `OpenAIRegexBuilder` — OpenAI as a third naming provider alongside `anthropic`
  and `deepseek` (`pip install parseforge[openai]`). Previously `deepseek`'s
  builder used the `openai` SDK too, but pointed at DeepSeek's own API — there
  was no way to actually use OpenAI's own models for naming until now.
  `--provider`/`--naming-provider` list `anthropic|deepseek|openai`
  automatically wherever they're used, since every occurrence already derives
  its choices from the same builder registry
- `models.yaml` gained an `openai` entry (default `gpt-5.4-mini`, matching the
  cheap/fast-tier default convention already used for `anthropic`/`deepseek`)
- Live-API test coverage for the new provider: `tests/real/naming/
  test_openai_naming.py` and `tests/real/generation/test_openai_generation.py`,
  mirroring the existing anthropic/deepseek real tests exactly, plus a new
  `openai_key` fixture in `tests/conftest.py`

### Fixed
- Two stale `--api-key` help strings (CLI and README) that only listed
  `ANTHROPIC_API_KEY`/`DEEPSEEK_API_KEY`, missing `OPENAI_API_KEY`

## v0.2.4 — 2026-08-02

### Changed
- **Breaking:** `pip install parseforge` no longer installs any AI-provider SDK —
  `anthropic` and `openai`/`deepseek` moved into optional extras
  (`pip install parseforge[anthropic]`, `parseforge[deepseek]`), mirroring
  `textfsm-ai` v0.6.0's own per-provider extras model. Both providers'
  `naming/providers/*.py` builders now import their SDK lazily, only when a
  client is actually constructed — a cache-hit naming lookup, or any purely
  local command (`canonical`/`readable`/`recognizers`/`integration`/
  `promotion`), never touches either package, and neither does importing the
  CLI itself
- `dev` extra keeps both `anthropic` and `openai` directly, so tests always
  exercise both providers instead of silently skipping
- Fixed `generation.generate()`'s docstring, which claimed to "never raise for
  a failed generation" — a missing provider SDK actually raises `ImportError`
  (uncaught, from `textfsm-ai`'s own lazy provider registry), which is correct
  and intentional, matching how a missing SDK is treated as a hard
  environment error everywhere else in this release, not a soft failure

### Added
- New `release` extra (`bump2version`, `build`) for `scripts/release.ps1` and
  local package builds — the one piece of tooling `requirements-dev.txt`
  covered that had no other home after being retired

### Removed
- `requirements.txt`/`requirements-dev.txt` — already stale (unconditional
  `anthropic`/`openai`/`netmiko`, an old `textfsm-ai>=0.5.1` floor) and
  duplicated what `pyproject.toml` now owns as the single source of truth.
  `docs.yml`'s deploy job (the only real consumer) didn't need any of
  parseforge's own runtime dependencies in the first place — it now installs
  `mkdocs`/`mkdocs-material`/`mike` directly

## v0.2.3 — 2026-07-31

### Added
- `drift.py` (SPEC.md §5 step 10): `check_drift()` runs an authoritative template
  against a new production sample, tracks a rolling match rate per variant in that
  cli-name's `drift-log.json`, and requeues failing samples into `trials/` as a new
  run so drift closes the loop back through generation/integration instead of being
  a one-off alert
- CLI: `check` (validate a connector/provider, or report what it needs before
  spending tokens), `generate-template`/`canonical`/`readable`/`recognizers`
  (one-shot generation and template inspection, no trial persistence), and
  `trial`/`integration`/`promotion` (config-file-driven workflow commands wrapping
  `pipeline.py`/`integration.py`/`promotion.py` end to end — `promotion` covers
  `AUTO_PROMOTED` mode only)
- CLI: `init-trial-config`/`init-generate-template-config` — write placeholder YAML
  configs for `trial --config`/`generate-template --config`, ready to fill in
- `parseforge/cli/config.py` — YAML config loading for the new config-driven commands
- `pipeline.TrialMetadata` gains a `note` field, for parity with
  `promotion.PromotionMetadata.note`

### Changed
- SPEC.md's `trials/`/`integration/`/`authoritative/` layout sections (§3.1–§3.3)
  rewritten to match the actual implementation — they'd described the
  pre-implementation single-template/single-winner design since before this
  session's integration/promotion work landed
- `trial.yaml`'s `naming_provider`/`generation_provider`/`generation_api_key`/
  `generation_model` fields collapsed into one shared `provider`/`api_key`/`model`,
  used for both naming and generation
- `run`'s `--generation-provider`/`--generation-api-key`/`--generation-model`
  renamed to `--provider`/`--api-key`/`--model`
- `promotion`'s `--match-rate-threshold`/`--min-sample-count` renamed to
  `--threshold`/`--min-samples`
- README.md and docs/index.md rewritten to describe the now-complete pipeline
  instead of the earlier "early-stage scaffold" status; README's `## Layout`
  section removed (duplicated each module's own docstring) in favor of a
  `## Reference` section linking the docs site and SPEC.md

## v0.2.2 — 2026-07-30

### Added
- Full trial pipeline (SPEC.md §5 steps 1–7): `pipeline.run_command_pipeline()` wires
  sampling → naming → generation → validation end to end, writing a per-run
  `summary.json` (command info, pass/fail, duration, token usage/cost, provider info)
- `naming`: `AnthropicRegexBuilder` and `DeepSeekRegexBuilder`, structured
  `LLMCLIResponse` with token usage and retryable-vs-fatal error classification;
  cost estimation via `textfsm-ai`'s pricing module
- `sampling`: Netmiko backend (`parseforge.sampling.netmiko`), generic + Cisco sandbox
  fixtures for live device testing
- `generation.py`: wired to `textfsm-ai`'s delivery pipeline for LLM-backed TextFSM
  template generation
- `validation.py`: `parse()`/`ParseResult` — thin TextFSM wrapper used by both
  integration clustering and promotion's `records.json` output
- `integration.py` (SPEC.md §5 step 8, §3.2, §6 multi-variant): clusters trial runs
  into output-schema groups, tracks per-variant template/record counts, and reports
  `total_case_count`/`total_passed_case_count` per case plus a project-wide
  `reference-summary.json` with `ratio_of_total`/`ratio_of_passed` at group and
  variant level — only trials that actually passed are eligible for clustering
- `promotion.py`: reworked into a project-wide, mode-aware promotion workflow —
  `AUTO_PROMOTED` (gate-driven, every qualifying group across every case) and
  `USER_REVIEWED` (scoped to caller-reviewed case/suffix requests); flat
  `authoritative/` layout (`template.textfsm`, `template-v2.textfsm`, ... — no
  per-group subdirectory); singular per-cli-name `golden.hash`/`artifact.json`
  reflecting the most recent promotion; project-wide append-only
  `authoritative-log.json` and per-run `authoritative-summary.json`;
  `history/` retention archiving prior content before it's overwritten by a
  differing re-promotion

### Changed
- Dropped the `<version>` path segment from trial/integration/authoritative
  storage paths — a cli-name's output structure rarely changes across minor OS
  versions, and when it does, `integration.py`'s group clustering is what's meant
  to catch it (SPEC.md §3, §3.1)
- Simplified `summary.json`: explicit `error` field, flattened `usage`/`provider_info`
  blocks, `--username-ref` CLI flag renamed to `--email`

### Removed
- Dead `store/` scaffold directory (never referenced by code) and its `.gitignore`
  entries

### Fixed
- `build_integration()` now checks a trial's own recorded pass/fail verdict before
  clustering it, instead of only re-deriving it by re-parsing the template against
  its own sample — closes a gap where a truncated/not-ready generation could still
  coincidentally self-parse and get counted as evidence

## v0.2.1 — 2026-07-16

### Added
- Initial project scaffold per SPEC.md: `naming`, `paths`, `pipeline`, `sampling`,
  `generation`, `validation`, `promotion` modules, packaged as `parseforge`
- `naming` package: LLM-backed cli-name resolver (`parseforge.naming.cli_name`) —
  builds a regex per CLI command via a pluggable `RegexBuilder`, validates it with
  `re.fullmatch`, and caches `cli-name -> pattern` in `~/.parseforge/.cli-name.json`
  so a given command is only ever sent to the LLM once
- `parseforge` CLI (`name`, `run` subcommands)
- `Tests` workflow (GitHub Actions) running pytest on push/PR to `main` and `develop`
- tox setup: `py39`/`py312` test envs, `lint`/`format` (ruff + black), `typecheck`
  (mypy), `docs` (`mkdocs build --strict`)
- `docs/index.md` and mkdocs (Material theme) with `mike`-based versioned docs
  deployment (`Deploy Docs` workflow, gated on lint/format/typecheck)
- `MANIFEST.in` for sdist packaging (LICENSE/README/SPEC included; tests/docs/store
  pruned)
- `bump2version` setup (`.bumpversion.cfg`) tracking version across
  `parseforge/__init__.py` and `pyproject.toml`
- `Makefile` and `scripts/release.ps1`: `bump-patch`/`bump-minor`/`bump-major`,
  `release-test` (tags `v$(VERSION)-test`, triggers TestPyPI), `release-prod`
  (tags `v$(VERSION)`, creates a GitHub Release, requires `main`)
- `publish-testpypi.yml` / `publish-pypi.yml` workflows — build + publish gated on
  the full test/lint/format/typecheck suite; validated end-to-end at `v0.2.1-test`
  (https://test.pypi.org/project/parseforge/0.2.1/)
