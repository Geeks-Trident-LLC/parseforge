# ParseForge

LLM-driven pipeline that forges, cross-validates, and promotes [TextFSM](https://github.com/google/textfsm)
templates from network device CLI output.

Full design plan: [SPEC.md](SPEC.md).

## Layout

```
parseforge/
  naming/         CLI command -> canonical cli-name (SPEC §2)
  paths.py        trials/integration/authoritative path resolution (SPEC §3)
  sampling/       device connection + command capture (SPEC §5 step 4)
  generation.py   LLM call + template extraction (SPEC §5 steps 5-6)
  validation.py   self-validation (SPEC §5 step 7)
  integration.py  cross-validation clustering into groups/variants (SPEC §3.2, §5 step 8)
  promotion.py    authoritative promotion gate (SPEC §3.3, §5 step 9)
  drift.py        drift monitoring against production samples (SPEC §5 step 10)
  pipeline.py     orchestrates naming/sampling/generation/validation (SPEC §4, §5 steps 1-7)
  cli/            `parseforge` command-line entry point
```

The runtime template tree (trials/ -> integration/ -> authoritative/) is generated at
`~/.parseforge/tests` by default (see `paths.DEFAULT_STORE_ROOT`), not checked into
this repo.

## Development

```
pip install -e ".[dev,sampling]"
pytest
```

## CLI

**Naming** — resolve a raw CLI command to its canonical cli-name (cached after the
first call, per SPEC §2):
```
parseforge name --vendor cisco --family catalyst9200 --os ios-xe --version 17.9.1 \
  show interface GE1.1 status
```

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
`recognizers.txt` to disk.

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
  --generation-provider anthropic --generation-api-key $ANTHROPIC_API_KEY \
  --generation-model claude-haiku-4-5-20251001 \
  show clock
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
naming_provider: anthropic
generation_provider: anthropic
generation_api_key: sk-...
generation_model: claude-haiku-4-5-20251001
commands:
  - show clock
  - show version
user: alice
workers: 1
```

**`integration`** — rebuild `integration/` for every case under `trials/` (SPEC §5
step 8):
```
parseforge integration
```

**`promotion`** — auto-promote every group that clears its gate (SPEC §5 step 9;
`AUTO_PROMOTED` mode only — `USER_REVIEWED` has no CLI surface yet):
```
parseforge promotion --user alice --match-rate-threshold 1.0 --min-sample-count 1
```

`trial`, `integration`, and `promotion` all default to `paths.DEFAULT_STORE_ROOT`
(`~/.parseforge/tests`); pass `--path <dir>` to point at a different store root.
