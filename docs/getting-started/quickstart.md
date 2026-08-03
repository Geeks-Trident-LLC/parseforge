# Quickstart

This walks through the CLI end to end: a single lookup, a reachability
check, one-shot template generation, then the full config-driven
`trial` → `integration` → `promotion` workflow. See
[Installation](installation.md) first if you haven't installed
`parseforge` yet.

The examples below use `anthropic` — swap in whichever
[provider](installation.md#for-using-the-cli-or-python-api) you installed
and set that provider's API key env var (`ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, ...).

## 1. Resolve a cli-name

Turn a raw CLI command into its canonical, indexed `cli-name` (SPEC §2).
The first call for a given command hits the LLM; every later call for the
same command is a free local cache hit:

```bash
parseforge name --vendor cisco --family catalyst9200 --os ios-xe --version 17.9.1 \
  show interface GE1.1 status
```

## 2. Check before you spend tokens

Validate a device connector or LLM provider is reachable before a real run:

```bash
parseforge check --connector netmiko --env cisco
parseforge check --provider anthropic
```

`--env=<name>` reads `<NAME>_SANDBOX_HOST`/`USERNAME`/`PASSWORD`/`DEVICE_TYPE`
from the environment. Run `check --connector netmiko` with no `--env` or
explicit `--host`/etc. and it prints what's needed instead of guessing.

## 3. Generate a template, no trial persisted

One-shot: sample → template → readable DSL → recognizers, with nothing
written under `trials/`:

```bash
parseforge generate-template --sample-file sample.txt \
  --provider anthropic --api-key $ANTHROPIC_API_KEY --model claude-haiku-4-5-20251001
```

Add `--out <dir>` to also write `template.textfsm`/`readable-dsl.txt`/
`recognizers.txt` to disk. Already have a template and just want to inspect
it? No LLM call needed:

```bash
parseforge canonical template.textfsm --sample sample.txt
parseforge readable template.textfsm --sample sample.txt
parseforge recognizers template.textfsm --sample sample.txt
```

## 4. Run the full pipeline: trial → integration → promotion

This is the persistent, evidence-accumulating workflow (SPEC §5) — the one
you'd actually run against real devices over time.

Write a config file once:

```bash
parseforge init-trial-config --out trial.yaml
```

```yaml title="trial.yaml"
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

Then run it, and promote whatever clears its match-rate gate:

```bash
parseforge trial --config trial.yaml
parseforge integration
parseforge promotion --user alice
```

- **`trial`** samples each command, generates a candidate template, and
  self-validates it — writing evidence under `trials/`. Repeat this any
  time new devices or commands come in; each run only adds evidence, it
  never discards prior trials.
- **`integration`** clusters every trial for a `cli-name` by the
  output-schema its records actually have, writing
  `integration/reference-summary.json`.
- **`promotion`** auto-promotes every group that clears its
  match-rate/sample-count gate into `authoritative/`; everything else is
  queued for human review. `promotion` always refreshes integration first,
  so running it alone after a `trial` is enough to pick up new evidence —
  a separate `integration` run is only useful if you want to inspect
  `reference-summary.json` without also promoting.

## Next steps

- Full CLI reference, the four providers with a non-standard auth shape,
  and the config-file schemas: see the
  [README](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/README.md#cli).
- Calling parseforge from Python instead of the CLI: see the
  [README's Python API section](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/README.md#python-api).
- Full design plan, storage tier layout, and open questions:
  [SPEC.md](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/SPEC.md).
