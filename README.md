# ParseForge

LLM-driven pipeline that forges, cross-validates, and promotes [TextFSM](https://github.com/google/textfsm)
templates from network device CLI output.

Full design plan: [SPEC.md](SPEC.md).

## Status

Early beta. The full pipeline is implemented and tested end to end — naming,
sampling, generation, self-validation, integration (output-schema group/variant
clustering), promotion (auto and human-reviewed), and drift monitoring — and
wired into the CLI below. A few things are intentionally not there yet:

- **`USER_REVIEWED` promotion has a library entry point but no CLI command**
  (`promotion.promote_user_reviewed()` works today; there's no
  `parseforge promotion --mode user-reviewed` yet). Deferred until real
  human-reviewed cases exist to show what a CLI/config shape for a list of
  case/suffix/gate requests should actually look like, rather than guessing
  ahead of need.
- **Batch sampling mode** (collect several samples per command before
  generating, SPEC.md §4) is designed but not built — the simpler
  per-command loop mode is the only one implemented.
- **One sampling connector** (Netmiko/SSH). The CLI's `--connector` registry
  is built to hold more without a redesign, but nothing else is wired in yet.

## Installation

```
pip install parseforge[anthropic]
```
`pip install parseforge` alone installs no AI-provider SDK at all — every
command that's pure local processing (`canonical`/`readable`/`recognizers`,
`integration`, `promotion`) works with nothing further. Anything that calls an
LLM (`name`, `check --provider`, `run`, `generate-template`, `trial`) needs the
extra for whichever provider it uses: `anthropic`, `openai`, `deepseek`,
`groq`, `xai`, `together`, `fireworks`, `perplexity`, or `openrouter`.
`--provider` defaults to `anthropic` wherever it isn't required, so that's
the one most setups need. `pip install parseforge[sampling]` adds Netmiko
for live device sampling; combine extras as needed, e.g.
`pip install parseforge[anthropic,openai,deepseek,groq,xai,together,fireworks,perplexity,openrouter,sampling]`.

## Development

```
pip install -e ".[dev,sampling]"
pytest
```
`dev` already includes both the `anthropic` and `openai` SDKs (tests exercise
all nine providers — `anthropic`, `openai`, `deepseek`, `groq`, `xai`,
`together`, `fireworks`, `perplexity`, `openrouter` share just those two
packages — and never silently skip) — add the specific `,<provider>` extra
explicitly only if installing outside of `dev`.

Linting/formatting/type-checking/docs run through tox instead of extras — see
`tox.ini` (`tox -e lint`/`format`/`typecheck`/`docs`), each installing its own
tools in an isolated env. Cutting a release needs `pip install -e ".[release]"`
(`bump2version`, `build`) — see `scripts/release.ps1`.

## CLI

Three kinds of commands: single lookups (`name`, `check`), one-shot inspection with
no persistence (`generate-template`, `canonical`/`readable`/`recognizers`), and the
config-driven `trial` → `integration` → `promotion` workflow that runs the full
pipeline end to end (see [Quickstart: end to end](#quickstart-end-to-end) below).

**Naming** — resolve a raw CLI command to its canonical cli-name (cached after the
first call, per SPEC §2):
```
parseforge name --vendor cisco --family catalyst9200 --os ios-xe --version 17.9.1 \
  show interface GE1.1 status
```
Still needs an LLM provider on a cache miss — `--provider` defaults to `anthropic`,
and `--api-key` falls back to that provider's own env var (`ANTHROPIC_API_KEY`/
`OPENAI_API_KEY`/`DEEPSEEK_API_KEY`). A cache hit (a command already seen before)
never touches the LLM, so no key is needed at all in that case.

**`check`** — validate a connector or provider before spending time/tokens on a real
run. With neither `--env` nor explicit connection flags, prints what a connector needs
instead of attempting a connection:
```
parseforge check --connector netmiko --env cisco
parseforge check --provider anthropic
```
`--env=<name>` reads `<NAME>_SANDBOX_HOST/USERNAME/PASSWORD/DEVICE_TYPE` from the
environment (the same convention the test suite uses for `CISCO_SANDBOX_*`).

**`generate-template`** — one-shot template generation, no trial persisted under
`trials/`:
```
parseforge generate-template --sample-file sample.txt \
  --provider anthropic --api-key $ANTHROPIC_API_KEY --model claude-haiku-4-5-20251001
```
Also accepts `--connector`/`--cmdline` (live sample) or `--config <file>` in place of
`--sample-file`; add `--out <dir>` to also write `template.textfsm`/`readable-dsl.txt`/
`recognizers.txt` to disk. `parseforge init-generate-template-config [--out <file>]`
writes a placeholder for that `--config` file, ready to fill in.

**`canonical` / `readable` / `recognizers`** — inspect an existing template file. No
LLM call; `--sample` is required to build the example records `textfsm-ai`'s DSL
compiler needs:
```
parseforge canonical template.textfsm --sample sample.txt
parseforge readable template.textfsm --sample sample.txt
parseforge recognizers template.textfsm --sample sample.txt
```

**`run`** — a single full trial (sample -> generate -> self-validate), SPEC §5 steps
1-7:
```
parseforge run --vendor cisco --family catalyst9200 --os ios-xe --version 17.9.1 \
  --host 10.0.0.1 --username admin --device-type cisco_ios \
  --provider anthropic --api-key $ANTHROPIC_API_KEY \
  --model claude-haiku-4-5-20251001 \
  show clock
```
`--provider`/`--api-key`/`--model` are for generation. Naming has its own separate
`--naming-provider`/`--naming-api-key`/`--naming-model`, defaulting independently
(`--naming-provider` defaults to `anthropic`; the other two fall back to that
provider's own env var/default model) — set them explicitly if naming needs a
different provider than generation.

**`init-trial-config`** — write a placeholder `trial.yaml` to fill in, instead of
writing one by hand:
```
parseforge init-trial-config --out trial.yaml
```

**`trial`** — every command in a YAML config file, optionally in parallel:
```
parseforge trial --config trial.yaml
```
```yaml
vendor: cisco
family: catalyst9200
os: ios-xe
version: 17.9.1
connector: netmiko
host: 10.0.0.1
username: admin
password: secret
device_type: cisco_ios
provider: anthropic
api_key: sk-...
model: claude-haiku-4-5-20251001
commands:
  - show clock
  - show version
user: alice
workers: 1
```
`provider`/`api_key`/`model` are one shared LLM source used for both naming and
generation. Use the `run` command's separate `--naming-*`/`--generation-*` flags
instead if a trial actually needs two different providers.

**`integration`** — rebuild `integration/` for every case under `trials/` (SPEC §5
step 8):
```
parseforge integration
```

**`promotion`** — auto-promote every group that clears its gate (SPEC §5 step 9;
`AUTO_PROMOTED` mode only — `USER_REVIEWED` has no CLI surface yet):
```
parseforge promotion --user alice --threshold 1.0 --min-samples 1
```

`trial`, `integration`, and `promotion` all default to `paths.DEFAULT_STORE_ROOT`
(`~/.parseforge/tests`); pass `--path <dir>` to point at a different store root.

### Quickstart: end to end

Run `trial` once per device/command batch (repeat as more devices or commands come
in — each run only adds new evidence, it never discards prior trials), then
`integration` and `promotion` any time you want the current evidence reflected in
`authoritative/`:

```bash
parseforge trial --config trial.yaml
parseforge integration
parseforge promotion --user alice
```

`integration` rebuilds `integration/reference-summary.json` from every trial
currently on disk, and `promotion` always refreshes integration itself before
evaluating any gate — so running `promotion` alone after a `trial` run is enough to
pick up new evidence; a separate `integration` run is only useful if you want to
inspect `reference-summary.json` without also promoting.

## Reference

- [Documentation site](https://geeks-trident-llc.github.io/parseforge/) ([source](./docs/index.md))
- [SPEC.md](SPEC.md) — full design plan and open questions
