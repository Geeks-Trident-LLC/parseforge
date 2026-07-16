# v0.2.1 — Initial Scaffold & Release Pipeline

## 🏗️ Project Scaffold
Full package layout per SPEC.md's design plan — naming, storage-tier path
resolution, and pipeline orchestration stubs.

## 🤖 LLM-Backed CLI Naming
`parseforge.naming.cli_name()` turns a raw CLI command into a canonical,
indexed `cli-name` via an LLM-built regex, validated with `re.fullmatch`,
and cached locally so a command is only ever sent to the LLM once:
```bash
parseforge name --vendor cisco --family catalyst9200 --os ios-xe --version 17.9.1 show interface GE1.1 status
```

## 📚 Docs Site
Live versioned documentation via mkdocs + mike:
https://geeks-trident-llc.github.io/parseforge/

## 🔧 Full Dev/Release Pipeline
- tox envs: test (py39/py312), lint, format, typecheck, docs
- `Makefile` / `scripts/release.ps1`: bump-patch/minor/major, release-test, release-prod
- CI: Tests, Deploy Docs, Publish to TestPyPI, Publish to PyPI — all wired and verified end-to-end

## 📦 Version
`0.1.0 → 0.2.1`
