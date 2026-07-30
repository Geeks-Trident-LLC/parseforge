# v0.2.2 — The Pipeline Comes Alive

## 🔄 End-to-End Trial Pipeline
`pipeline.run_command_pipeline()` now runs the full SPEC.md §5 flow — sample a
device, name the CLI command, generate a TextFSM template via LLM, validate it —
and records everything in a per-run `summary.json`.

## 🧬 Integration: Grouping Trials into Evidence
`integration.py` clusters passed trial runs by output schema into groups, so
templates covering the same command's different valid outputs (hardware/firmware
variants, SPEC.md §6) accumulate as separate, trackable variants instead of
overwriting one another. A new `reference-summary.json` reports match-rate ratios
project-wide.

## 🚦 Promotion: Gated, Mode-Aware, Auditable
`promotion.py` is now a real workflow, not a stub:
- **AUTO_PROMOTED** — every group that clears its gate (match-rate threshold +
  minimum sample count) across every case gets promoted automatically
- **USER_REVIEWED** — scoped, suffixed promotions for snapshots a human has
  already reviewed
- `golden.hash` + `artifact.json` per cli-name, an append-only
  `authoritative-log.json`, and `history/` retention of superseded content

## 🧹 Cleanup
Dropped the unused `store/` scaffold directory, the `<version>` path segment
(superseded by group-based clustering), and dead code from earlier stub-era
scaffolding.

## 📦 Version
`0.2.1 → 0.2.2`

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
