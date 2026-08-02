# v0.2.6 — Eight New Naming Providers

## 🚀 Bring Your Own Model
`parseforge` now speaks to eleven LLM providers for cli-name resolution, up
from three. Each new provider follows the same pattern already established
for `anthropic`/`openai`/`deepseek`: an optional extra
(`pip install parseforge[<provider>]`), a lazily-imported SDK (never touched
unless you actually make a call), and its own environment variable for the
API key:

| Provider | Extra | Env var | Default model |
|---|---|---|---|
| Groq | `parseforge[groq]` | `GROQ_API_KEY` | `llama-3.1-8b-instant` |
| xAI | `parseforge[xai]` | `XAI_API_KEY` | `grok-3-mini` |
| Together AI | `parseforge[together]` | `TOGETHER_API_KEY` | `meta-llama/Llama-3.1-8B-Instruct-Turbo` |
| Fireworks AI | `parseforge[fireworks]` | `FIREWORKS_API_KEY` | `accounts/fireworks/models/llama-v3p1-8b-instruct` |
| Perplexity | `parseforge[perplexity]` | `PERPLEXITY_API_KEY` | `sonar` |
| OpenRouter | `parseforge[openrouter]` | `OPENROUTER_API_KEY` | `google/gemini-2.5-flash-lite` |
| Moonshot AI (Kimi) | `parseforge[moonshot]` | `MOONSHOT_API_KEY` | `moonshot-v1-8k` |
| Cerebras | `parseforge[cerebras]` | `CEREBRAS_API_KEY` | `llama3.1-8b` |

All eight are pure `openai`-SDK-compatible providers (same request/response
shape, just a different `base_url`), so no new SDK dependency was needed —
`--provider anthropic|deepseek|openai|groq|xai|together|fireworks|perplexity|openrouter|moonshot|cerebras`
is now a single flag away.

## ✅ Live Test Coverage
Every new provider ships with the same real-API test pair as the existing
ones (naming + generation), gated behind `pytest --real` and that provider's
API key — nothing runs, or costs tokens, unless you opt in.

## 📦 Version
`0.2.5 → 0.2.6`

# v0.2.5 — OpenAI Joins the Party

## 🤖 A Real OpenAI Naming Provider
`deepseek`'s builder always used the `openai` SDK under the hood — but pointed
at DeepSeek's own API, not OpenAI's. `OpenAIRegexBuilder` closes that gap:
`pip install parseforge[openai]` gets you OpenAI's own models (`gpt-5.4-mini`
by default) for cli-name resolution, same lazy-import/optional-extra treatment
as `anthropic` and `deepseek` already have.

## ✅ Live Test Coverage
New real tests for the OpenAI provider (naming + generation), gated the same
way as every other live-API test in this project — `pytest --real` plus
`OPENAI_API_KEY`.

## 📦 Version
`0.2.4 → 0.2.5`

# v0.2.4 — A Minimal Core, Finally

## 📦 `pip install parseforge` Is Actually Minimal Now
Every AI-provider SDK (`anthropic`, `openai`) moved out of the base install
into opt-in extras — `pip install parseforge[anthropic]` or
`parseforge[deepseek]` — matching the same move `textfsm-ai` v0.6.0 made
upstream. Anything that's pure local processing (`canonical`/`readable`/
`recognizers`, `integration`, `promotion`) now works with nothing beyond the
core install; only an actual LLM call needs the matching extra, and you get a
clear, actionable error if it's missing rather than a crash at import time.

## 🧹 Cleanup
- Retired `requirements.txt`/`requirements-dev.txt` — stale duplicates of
  `pyproject.toml`, which is now the single source of truth for every
  dependency, including a new `release` extra for `bump2version`/`build`
- Fixed a docstring in `generation.py` that claimed to never raise, when a
  missing provider SDK correctly does

## 📦 Version
`0.2.3 → 0.2.4`

# v0.2.3 — Drift Monitoring and a Real CLI

## 🌊 Drift Monitoring
`drift.py` closes SPEC.md's last unimplemented pipeline stage: checking an
authoritative template against new production samples, tracking a rolling match
rate per variant, and requeuing failing samples back into `trials/` so drift
feeds back into the pipeline instead of just being an alert.

## 🖥️ A Real CLI
Ten new commands, on top of `name`/`run`: `check` (validate a connector/provider
before spending tokens), `generate-template`/`canonical`/`readable`/`recognizers`
(one-shot generation and inspection, no persistence), `trial`/`integration`/
`promotion` (config-driven, run the full pipeline end to end), and
`init-trial-config`/`init-generate-template-config` to scaffold those config files
instead of hand-writing them.

## 🧹 Cleanup
- SPEC.md's storage-tier sections now match the real implementation, not the
  pre-implementation design they still described
- `trial.yaml`, `run`, and `promotion`'s CLI flags simplified to shorter, more
  consistent names
- README.md and docs/index.md rewritten for the now-complete pipeline

## 📦 Version
`0.2.2 → 0.2.3`

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
