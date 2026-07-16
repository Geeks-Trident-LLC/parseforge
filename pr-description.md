## Summary
This PR establishes the initial ParseForge project scaffold and full
development/release tooling per SPEC.md's design plan, culminating in v0.2.1.

## What's Included

### Project Scaffold
- Package layout per SPEC.md: `naming`, `paths`, `pipeline`, `sampling`,
  `generation`, `validation`, `promotion`
- `naming` fully implemented: LLM-backed `cli_name()` resolver with on-disk
  caching, `RegexBuilder` protocol, `re.fullmatch` self-validation
- `parseforge` CLI (`name`, `run`)
- Storage tier scaffold (`store/{trials,integration,authoritative}/`)

### Dev Tooling
- tox: `py39`/`py312`, `lint`, `format`, `typecheck`, `docs` envs
- ruff + black + mypy configured and clean across the codebase
- `MANIFEST.in` for sdist packaging

### Documentation
- `docs/index.md` + mkdocs (Material theme)
- Versioned docs deployment via `mike`, live at
  https://geeks-trident-llc.github.io/parseforge/

### CI/CD
- `Tests` workflow (pytest on push/PR to `main`/`develop`)
- `Deploy Docs` workflow (lint/format/typecheck gate -> mike deploy)
- `publish-testpypi.yml` / `publish-pypi.yml` (build + publish, gated on full suite)
- `bump2version`, `Makefile`, `scripts/release.ps1`
  (`bump-patch`/`minor`/`major`, `release-test`, `release-prod`)

## Release Artifacts
- CHANGELOG updated for v0.2.1
- Release notes generated
- Version bumped 0.1.0 -> 0.2.1

## Testing
- Full test suite passing (11 tests)
- `tox -e lint` / `format` / `typecheck` / `docs` all clean
- TestPyPI release validated (`v0.2.1-test` -> https://test.pypi.org/project/parseforge/0.2.1/)
