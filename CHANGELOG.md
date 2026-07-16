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
