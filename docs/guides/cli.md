# CLI Guide

Three kinds of commands: single lookups (`name`, `check`), one-shot
inspection with no persistence (`generate-template`,
`canonical`/`readable`/`recognizers`), and the config-driven `trial` →
`integration` → `promotion` workflow that runs the full pipeline end to
end (see [Quickstart](../getting-started/quickstart.md) for a walkthrough).

Every command below assumes `parseforge` is installed with at least one
provider extra — see [Installation](../getting-started/installation.md).
The four providers with a non-standard auth shape (`azure`, `vertexai`,
`bedrock`, `oci`) each need extra flags — see [Providers](providers.md).

## `name`

Resolve a raw CLI command to its canonical cli-name (cached after the
first call, per SPEC §2):

```bash
parseforge name --vendor cisco --family catalyst9200 --os ios-xe --version 17.9.1 \
  show interface GE1.1 status
```

Still needs an LLM provider on a cache miss — `--provider` defaults to
`anthropic`, and `--api-key` falls back to that provider's own env var
(`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`DEEPSEEK_API_KEY`/etc.). A cache hit
(a command already seen before) never touches the LLM, so no key is
needed at all in that case.

## `check`

Validate a connector or provider before spending time/tokens on a real
run. With neither `--env` nor explicit connection flags, prints what a
connector needs instead of attempting a connection:

```bash
parseforge check --connector netmiko --env cisco
parseforge check --provider anthropic
```

`--env=<name>` reads `<NAME>_SANDBOX_HOST/USERNAME/PASSWORD/DEVICE_TYPE`
from the environment (the same convention the test suite uses for
`CISCO_SANDBOX_*`).

## `generate-template`

One-shot template generation, no trial persisted under `trials/`:

```bash
parseforge generate-template --sample-file sample.txt \
  --provider anthropic --api-key $ANTHROPIC_API_KEY --model claude-haiku-4-5-20251001
```

Also accepts `--connector`/`--cmdline` (live sample) or `--config <file>`
in place of `--sample-file`; add `--out <dir>` to also write
`template.textfsm`/`readable-dsl.txt`/`recognizers.txt` to disk.
`parseforge init-generate-template-config [--out <file>]` writes a
placeholder for that `--config` file, ready to fill in.

## `canonical` / `readable` / `recognizers`

Inspect an existing template file. No LLM call; `--sample` is required to
build the example records `textfsm-ai`'s DSL compiler needs:

```bash
parseforge canonical template.textfsm --sample sample.txt
parseforge readable template.textfsm --sample sample.txt
parseforge recognizers template.textfsm --sample sample.txt
```

## `run`

A single full trial (sample → generate → self-validate), SPEC §5 steps 1-7:

```bash
parseforge run --vendor cisco --family catalyst9200 --os ios-xe --version 17.9.1 \
  --host 10.0.0.1 --username admin --device-type cisco_ios \
  --provider anthropic --api-key $ANTHROPIC_API_KEY \
  --model claude-haiku-4-5-20251001 \
  show clock
```

`--provider`/`--api-key`/`--model` are for generation (`--api-key` isn't
required for `--provider vertexai`/`--provider bedrock`/`--provider oci`).
Naming has its own separate `--naming-provider`/`--naming-api-key`/
`--naming-model`, defaulting independently (`--naming-provider` defaults
to `anthropic`; the other two fall back to that provider's own env
var/default model) — set them explicitly if naming needs a different
provider than generation.

`--provider azure`/`--naming-provider azure` each get their own
`--endpoint`/`--api-version`/`--deployment` (generation) and
`--naming-endpoint`/`--naming-api-version`/`--naming-deployment` (naming);
`--provider vertexai`/`--naming-provider vertexai` similarly get
`--gcp-project`/`--gcp-location` and `--naming-gcp-project`/
`--naming-gcp-location`; `--provider bedrock`/`--naming-provider bedrock`
get `--region` and `--naming-region`; `--provider oci`/`--naming-provider
oci` get `--region`/`--compartment-id` and
`--naming-region`/`--naming-compartment-id` — see
[Providers](providers.md) for what each one is for.

## `init-trial-config`

Write a placeholder `trial.yaml` to fill in, instead of writing one by hand:

```bash
parseforge init-trial-config --out trial.yaml
```

## `trial`

Every command in a YAML config file, optionally in parallel:

```bash
parseforge trial --config trial.yaml
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

`provider`/`api_key`/`model` are one shared LLM source used for both
naming and generation. Use `run`'s separate `--naming-*`/generation-side
flags instead if a trial actually needs two different providers.

For `provider: azure`, also set `endpoint`/`api_version`/`deployment`
(`deployment` replaces `model`). For `provider: vertexai`, set
`project`/`location` instead — `api_key` can be omitted entirely (Vertex
AI authenticates via GCP's own Application Default Credentials). For
`provider: bedrock`, set `region` instead — `api_key` can likewise be
omitted entirely (Bedrock authenticates via AWS's own credential chain).
For `provider: oci`, set `region`/`compartment_id` instead — `api_key`
can likewise be omitted entirely (OCI authenticates via local
request-signing credentials in `~/.oci/config`). See
`parseforge init-trial-config`'s generated placeholder for the exact keys.

## `integration`

Rebuild `integration/` for every case under `trials/` (SPEC §5 step 8):

```bash
parseforge integration
```

## `promotion`

Auto-promote every group that clears its gate (SPEC §5 step 9;
`AUTO_PROMOTED` mode only — `USER_REVIEWED` has no CLI surface yet):

```bash
parseforge promotion --user alice --threshold 1.0 --min-samples 1
```

`trial`, `integration`, and `promotion` all default to
`paths.DEFAULT_STORE_ROOT` (`~/.parseforge/tests`); pass `--path <dir>`
to point at a different store root.

## Quickstart: end to end

Run `trial` once per device/command batch (repeat as more devices or
commands come in — each run only adds new evidence, it never discards
prior trials), then `integration` and `promotion` any time you want the
current evidence reflected in `authoritative/`:

```bash
parseforge trial --config trial.yaml
parseforge integration
parseforge promotion --user alice
```

`integration` rebuilds `integration/reference-summary.json` from every
trial currently on disk, and `promotion` always refreshes integration
itself before evaluating any gate — so running `promotion` alone after a
`trial` run is enough to pick up new evidence; a separate `integration`
run is only useful if you want to inspect `reference-summary.json`
without also promoting.
