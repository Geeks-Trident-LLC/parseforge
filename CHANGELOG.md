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
