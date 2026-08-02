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
