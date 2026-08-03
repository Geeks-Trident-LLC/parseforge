# Python API

Everything the CLI does is also a plain Python call — `parseforge/api.py`
is the single supported place to import from (also re-exported at the
package root). See the [API Reference](../reference/api.md) for the full
list of what's exported.

## The full pipeline, one call

`run_command_pipeline()` runs SPEC.md §5 steps 1-7 (naming → sampling →
generation → self-validation) for a single command, and writes the
result under a trial directory the same way `parseforge run` does:

```python
from parseforge import CliContext, LLMProviderConfig, run_command_pipeline
from parseforge.naming import AnthropicRegexBuilder
from parseforge.sampling import DeviceConnection
from parseforge.sampling.backends import NetmikoSampler

result = run_command_pipeline(
    "show clock",
    CliContext(vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"),
    DeviceConnection(host="10.0.0.1", username="admin", password="secret", device_type="cisco_ios"),
    AnthropicRegexBuilder(api_key="sk-..."),
    NetmikoSampler(),
    LLMProviderConfig(provider="anthropic", api_key="sk-...", model="claude-haiku-4-5-20251001"),
)
print(result.cli_name, result.passed, result.total_usage)
```

`NetmikoSampler` needs the `sampling` extra (`pip install
parseforge[sampling]`). `AnthropicRegexBuilder` needs the matching
provider extra — see [Providers](providers.md) for every provider's
builder class and non-standard-auth parameters.

## Individual stages

Each pipeline stage is also callable on its own — useful for scripting a
custom workflow, or testing one stage in isolation.

### Naming only

```python
from parseforge import CliContext, cli_name
from parseforge.naming import AnthropicRegexBuilder

context = CliContext(vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1")
name = cli_name(
    "show interface GE1.1 status", context, builder=AnthropicRegexBuilder(api_key="sk-...")
)
# "show-interface-var1-status" -- cached locally, so a repeat call for the
# same command never touches the LLM again.
```

### Sampling only

```python
from parseforge.sampling import DeviceConnection, sample
from parseforge.sampling.backends import NetmikoSampler

connection = DeviceConnection(
    host="10.0.0.1", username="admin", password="secret", device_type="cisco_ios"
)
output = sample(NetmikoSampler(), connection, "show clock")
```

### Generation only

```python
from parseforge import generate

result = generate(
    output,  # a raw sample string, e.g. from sample() above
    "anthropic",
    "sk-...",
    "claude-haiku-4-5-20251001",
)
print(result.template, result.readable_dsl, result.recognizers, result.usage)
```

### Self-validation only

```python
from parseforge import parse

validated = parse(result.template, output)
print(validated.passed, validated.records, validated.errors)
```

## Integration and promotion

Run after one or more `trial`/`run_command_pipeline()` calls have
written evidence under a store root:

```python
from pathlib import Path

from parseforge import (
    PromotionGate,
    PromotionMetadata,
    build_integration,
    discover_device_keys,
    promote_auto,
    write_reference_summary,
)

store_root = Path.home() / ".parseforge" / "tests"

# Cluster every trial for each cli-name by output schema.
for key in discover_device_keys(store_root):
    build_integration(store_root, key)
write_reference_summary(store_root)

# Auto-promote every group that clears its match-rate/sample-count gate.
result = promote_auto(
    store_root,
    PromotionMetadata(user="alice"),
    PromotionGate(match_rate_threshold=1.0, min_sample_count=1),
)
print(result.promoted, result.unqualified)
```

## Drift monitoring

Check an already-promoted, authoritative template against a fresh
production sample:

```python
from parseforge import DeviceKey, check_drift

key = DeviceKey(vendor="cisco", family="catalyst9200", os="ios-xe", cli_name="show-clock")
result = check_drift(store_root, key, new_sample_text)
print(result.match_rate, result.status)
```

A failing sample gets fed back into the pipeline as a new trial by design
— re-run `trial`/`run_command_pipeline()` for that command to add it as
evidence, then `promotion` again once enough new evidence accumulates.
