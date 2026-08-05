# v0.3.2 — Same 18 Providers, One Engine Underneath

## 🔌 18 Hand-Rolled SDK Integrations Become One
Every naming provider — Anthropic, OpenAI, DeepSeek, Groq, xAI, Together,
Fireworks, Perplexity, OpenRouter, Moonshot, Cerebras, Mistral, Cohere,
Azure OpenAI, Gemini, Vertex AI, Bedrock, OCI — used to be its own file,
each hand-rolling a client, an error-classification scheme, and response
parsing for that vendor's specific SDK. They're now one generic builder
backed by [anyask](https://github.com/Geeks-Trident-LLC/anyask), a
standalone sibling package (same author/org as textfsm-ai) that already
solves exactly this problem across the same 18 vendors.

Nothing changes for anyone calling parseforge: every
`<Provider>RegexBuilder` class, every CLI flag, every default model is
exactly where it was. `pip install parseforge[<provider>]` now pulls in
`anyask[<provider>]` instead of the provider's raw SDK directly — same
install command, one less thing for this repo to independently maintain
per vendor.

## 📝 A README for Everyone, Not Just Contributors
The README led with implementation details — trial/integration/promotion
internals, an eighteen-provider list — before ever saying what the tool
actually does or why you'd reach for it. It now opens with "What is
ParseForge?" and "Why do you need ParseForge?", written for someone who's
never touched TextFSM, and moves the provider list into its own
"Supported providers" section. The Status section is gone — the pipeline
is fully built now, so a caveats list calling it "early beta" was stale.
Also fixed: the `SPEC.md` link, which pointed at a path relative to the
GitHub repo — fine on GitHub, a dead link on PyPI, where README.md is
shown without the rest of the repo alongside it.

## 🧰 Lighter Release Tooling
Version lookups (`Makefile`, `scripts/release.ps1`, the docs-deploy
workflow) parsed `pyproject.toml` with `tomllib`, falling back to `tomli`
on older Python — now they just regex-match the `version = "..."` line
directly. One less dependency to keep installed, and `release.ps1`
doesn't need to shell out to Python at all for this step anymore.

## 📦 Version
`0.3.1 → 0.3.2`

# v0.3.1 — Docs That Actually Cover Everything

## 📖 Five New Pages, One Front Door
`README.md` was doing double duty as both a pitch and a reference manual,
and the docs site had exactly two pages. This release moves the reference
material where it belongs:

- **[Providers](https://geeks-trident-llc.github.io/parseforge/guides/providers/)** — all eighteen at a glance, plus a full breakdown of the four with non-standard auth (Azure, Vertex AI, Bedrock, OCI).
- **[CLI Guide](https://geeks-trident-llc.github.io/parseforge/guides/cli/)** — every command, in full, no longer squeezed into a README section.
- **[Python API](https://geeks-trident-llc.github.io/parseforge/guides/python-api/)** — the whole pipeline in one call, and every stage called on its own.
- **[API Reference](https://geeks-trident-llc.github.io/parseforge/reference/api/)** — every public name, organized by pipeline stage.
- **[Changelog](https://geeks-trident-llc.github.io/parseforge/changelog/)** — this file, live on the docs site via a snippet include, so it's never out of sync with the real one.

`README.md` is now what a README should be: what parseforge does, why the
trial → integration → promotion workflow exists (it's a Human-in-the-Loop
review system, not a one-shot template generator), a three-line install,
and links to everything else.

## 📦 Version
`0.3.0 → 0.3.1`

# v0.3.0 — A Real Public API, and a Dependency Diet

## 🚪 `from parseforge import ...` Now Actually Means Something
Every provider was in place, but the package's own front door was empty —
`parseforge/__init__.py` exported nothing but `__version__`. This release
adds `parseforge/api.py`, one entry point per pipeline stage, re-exported
at the root the same way `textfsm-ai` does its own:

```python
from parseforge import CliContext, LLMProviderConfig, run_command_pipeline
```

`cli_name`, `sample`, `generate`, `parse`, `run_command_pipeline`,
`build_integration`, `promote_auto`, `check_drift` — plus the
dataclasses/enums each one hands back. Provider-specific naming builders
stay where they already made sense (`parseforge.naming`), so this isn't a
bloated everything-and-the-kitchen-sink export — it's the actual supported
surface, finally documented as one.

## 🧮 Total Usage, Not Just Two Separate Numbers
`summary.json` used to report naming and generation token usage as two
disconnected sub-objects. A quick audit confirmed both were individually
correct — generation usage was already summed across every retry by
textfsm-ai itself — but nothing ever added them together. `TrialResult`
now carries a `total_usage` field, and `run`/`trial` print it directly.

## ✂️ Cost Estimation Is Gone
textfsm-ai 0.7.0 made a deliberate call: maintaining a per-provider,
per-model price table for eighteen providers is a different job than
turning samples into templates, and it doesn't belong in a
template-generation tool. `parseforge` follows suit — `estimated_cost` is
gone from `TokenUsage` everywhere, and `naming/providers/cost.py` is
deleted. (`models.yaml` got the same treatment: a flat `provider: model`
map instead of a `default`/`supported`/`deprecated` structure nobody but
its own tests ever read the extra two fields of.)

If you're pulling in `textfsm-ai` directly for the first time since
`v0.2.12`: that release briefly pinned `<0.7.0` to avoid a fresh install
silently breaking on the removed pricing module. This release removes
that pin — parseforge now expects `textfsm-ai>=0.7.1`.

## 📚 A Front Door for the Docs, Too
The docs site was one page mixing concepts with a truncated "Try it"
snippet. It now has a proper Getting Started section:
[Installation](https://geeks-trident-llc.github.io/parseforge/getting-started/installation/)
and
[Quickstart](https://geeks-trident-llc.github.io/parseforge/getting-started/quickstart/) —
plus one `requirements/dev-<provider>.txt` per provider, so cloning the
repo and testing a single provider no longer means installing every
other provider's SDK first.

## 📦 Version
`0.2.12 → 0.3.0`

# v0.2.12 — Bedrock and OCI Round Out the Cloud Trio

## ☁️ AWS and Oracle Join Google in the No-API-Key Club
Two more providers, two more ways to skip the API key entirely:

```
pip install parseforge[bedrock,oci]
```
```
parseforge name --provider bedrock --region us-east-1 show version
parseforge name --provider oci --region us-ashburn-1 \
  --compartment-id ocid1.compartment.oc1..xxxx show version
```

**Bedrock** authenticates via AWS's own credential chain and only needs a
region — the simplest of the three cloud providers so far. **OCI** is the
most involved provider yet: it signs every request cryptographically
against local `~/.oci/config` credentials, and needs a *compartment ID* on
top of region (the OCID of the compartment/tenancy that bills and scopes
each request) — a third parameter no other provider has required.

Error handling split along familiar lines: Bedrock raises a family of
named exception classes classified by name (like Anthropic and OpenAI),
while OCI raises one exception class with a status code (like Mistral,
Cohere, Azure, and Gemini).

## 📦 Version
`0.2.11 → 0.2.12`

# v0.2.11 — Vertex AI: No API Key Required

## 🔑 A Second Provider Without an API Key
Sixteen providers in, and Vertex AI breaks the mold the same way Azure did
— just differently. No `--api-key` at all: it authenticates through GCP's
own Application Default Credentials, and needs a project and a region
instead.

```
pip install parseforge[vertexai]
```
```
parseforge name --provider vertexai --gcp-project my-project \
  --gcp-location us-central1 show version
```

Under the hood it's the same `google-genai` SDK Gemini already uses — just
pointed at GCP's enterprise billing instead of the public API — so Vertex
AI serves the identical Gemini model catalog. The trickiest part wasn't
the SDK, it was naming the new flags: `run` already had a `--project` flag
(a free-text trial label), so Vertex AI's GCP project needed a
`--gcp-project`/`--gcp-location` pair to avoid a collision.

## 📦 Version
`0.2.10 → 0.2.11`

# v0.2.10 — Gemini Joins the Native-SDK Club

## ✨ Fifteen Providers Now
`parseforge` can now resolve cli-names with Google's Gemini models too:

```
pip install parseforge[gemini]
```
```
parseforge name --provider gemini --api-key $GEMINI_API_KEY show version
```

Like Mistral, Cohere, and Azure before it, Gemini's official SDK
(`google-genai`) has its own client shape rather than the OpenAI-compatible
dialect most providers speak — `GeminiRegexBuilder` talks to it directly,
with the same status-code-based error classification the other native-SDK
providers already use. Two small Gemini-specific quirks got ironed out
along the way: its `finish_reason` is an enum that stringifies ugly
(`"FinishReason.STOP"`) unless you reach for `.value`, and "thinking mode"
is switched off by default so a naming call doesn't pay for reasoning it
doesn't need.

## 📦 Version
`0.2.9 → 0.2.10`

# v0.2.9 — Azure OpenAI, the Odd One Out

## ☁️ A Provider That Breaks the Mold
Every provider so far — thirteen of them — needed just an API key and a
model name. Azure OpenAI doesn't work that way: there's no public
`base_url` (it's your own Azure resource) and no fixed model catalog
(it's your own account-specific *deployment* name instead). `parseforge`
now handles that shape natively:

```
pip install parseforge[azure]
```
```
parseforge name --provider azure --api-key $AZURE_API_KEY \
  --endpoint https://my-resource.openai.azure.com \
  --deployment my-gpt4-deployment \
  show version
```

New `--endpoint`/`--api-version`/`--deployment` options show up wherever
`--provider azure` is usable — `name`, `run` (both its naming and
generation sides), `check --provider`, `generate-template`, and both
`trial.yaml`/`generate-template.yaml` config files — falling back to
`AZURE_ENDPOINT`/`AZURE_API_VERSION`/`AZURE_DEPLOYMENT` the same way every
other provider's `--api-key` falls back to its own env var.

## 🐛 Two Bugs Caught Before They Shipped
Building out Azure's real tests surfaced two gaps that would have bitten
real users:
- A trial config for `azure` would have crashed with a raw `TypeError`
  (Azure has no `model` parameter, but `model` is always present in a
  trial config) — fixed so `deployment` now correctly takes over instead.
- Generation would have silently sent an empty `api_version` to a live
  Azure endpoint if you didn't set one explicitly — fixed with the same
  sensible default the naming side already had.

## 📦 Version
`0.2.8 → 0.2.9`

# v0.2.8 — Native-SDK Providers: Mistral and Cohere

## 🧬 Beyond OpenAI-Compatible
Every provider so far — even DeepSeek, Groq, xAI, and the rest — spoke the
same OpenAI-compatible `chat.completions` dialect under the hood. Mistral
and Cohere don't: both ship their own native Python SDKs with their own
client shapes, error types, and response formats. `parseforge` now speaks
both:

- **Mistral** (`pip install parseforge[mistral]`, `MISTRAL_API_KEY`,
  default `mistral-small-latest`) — via the native `mistralai` SDK's
  `client.chat.complete()`.
- **Cohere** (`pip install parseforge[cohere]`, `COHERE_API_KEY`, default
  `command-light`) — via the native `cohere` SDK's `ClientV2.chat()`.

Both required their own error-classification logic (status-code-based
instead of the shared exception-class-name approach every other provider
uses) since neither SDK raises OpenAI/Anthropic-shaped exceptions. Both are
pinned to exact versions (`mistralai==1.10.0`, `cohere==5.21.1`) — the last
releases of each SDK supporting Python 3.9, matching the same floor
`parseforge` itself supports.

That brings the provider count to **thirteen**.

## ✅ Live Test Coverage
Same real-API test pair as every other provider (naming + generation),
gated behind `pytest --real` and the provider's own API key.

## 📦 Version
`0.2.6 → 0.2.8` (0.2.7 — the Mistral provider alone — was bumped but never
published to production; this release folds it in alongside Cohere)

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
