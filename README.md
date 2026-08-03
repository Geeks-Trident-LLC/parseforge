# ParseForge

LLM-driven pipeline that forges, cross-validates, and promotes [TextFSM](https://github.com/google/textfsm)
templates from network device CLI output.

Full design plan: [SPEC.md](SPEC.md).

## Features

- **Trial → integration → promotion: a Human-in-the-Loop review workflow,
  not a one-shot generator.** Every LLM-generated template starts as
  unreviewed evidence in `trials/`. `integration` clusters every trial for
  a command by the *output schema* its parsed records actually have, not
  exact template text — a command's output can legitimately vary by
  hardware/firmware, so distinct schemas become separate, independently
  tracked groups instead of one hand-picked "winner." `promotion` then
  auto-promotes any group whose match rate against every known sample
  clears a configurable gate straight into `authoritative/`; anything
  short of that gate is queued for human review instead of silently
  shipped. A human-reviewed promotion is recorded as a named snapshot
  alongside whatever's currently live, never silently overwriting it —
  so review effort goes only where the evidence is actually ambiguous.
- **Eighteen LLM providers, one interface.** Anthropic, OpenAI, DeepSeek,
  Groq, xAI, Together, Fireworks, Perplexity, OpenRouter, Moonshot,
  Cerebras, Mistral, Cohere, Azure OpenAI, Gemini, Vertex AI, Amazon
  Bedrock, and Oracle Cloud (OCI) — including four with non-standard auth
  (deployment names, GCP Application Default Credentials, AWS's
  credential chain, OCI request-signing) handled transparently. Naming
  and generation can use two different providers in the same trial. See
  [Providers](https://geeks-trident-llc.github.io/parseforge/guides/providers/).
- **Self-caching cli-name resolution.** A raw CLI command
  (`show interface GE1.1 status`) only ever costs LLM tokens once — it's
  resolved to a canonical, indexed name
  (`show-interface-var1-status`) and cached locally; every later trial for
  that command is a free lookup.
- **Self-validation, not just "the LLM said so."** Every generated
  template is immediately run against its own sample before being
  recorded as passed — a template that doesn't actually parse the output
  it was generated from never gets a chance to look good on paper.
- **Drift monitoring.** An authoritative template is periodically checked
  against new production samples; a failing sample feeds back into the
  pipeline as a new trial automatically, closing the loop instead of just
  logging an alert.
- **CLI and Python API, same underlying calls.** Everything the CLI does
  — `run`, `trial`, `integration`, `promotion` — is one function call in
  Python too. See the
  [Python API guide](https://geeks-trident-llc.github.io/parseforge/guides/python-api/).

## Status

Early beta. The full pipeline is implemented and tested end to end — naming,
sampling, generation, self-validation, integration (output-schema group/variant
clustering), promotion (auto and human-reviewed), and drift monitoring — and
wired into the CLI. A few things are intentionally not there yet:

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

```bash
# minimal install, no AI-provider SDK
pip install parseforge

# with a provider extra, e.g. anthropic
pip install parseforge[anthropic]

# local development
pip install -e ".[dev,sampling]"
```

For the full extras list (all eighteen providers, `sampling`, combining
extras, per-provider `requirements/` files, and the dev/test/release
setup), see
[Installation](https://geeks-trident-llc.github.io/parseforge/getting-started/installation/).

## Reference

- [Documentation site](https://geeks-trident-llc.github.io/parseforge/) ([source](./docs/index.md))
- [Quickstart](https://geeks-trident-llc.github.io/parseforge/getting-started/quickstart/) — a full walkthrough, from a single lookup to the end-to-end workflow
- [Providers](https://geeks-trident-llc.github.io/parseforge/guides/providers/) — every provider's extra, auth requirements, and default model
- [CLI Guide](https://geeks-trident-llc.github.io/parseforge/guides/cli/) — every command, in full
- [Python API guide](https://geeks-trident-llc.github.io/parseforge/guides/python-api/) — calling parseforge from Python instead of the CLI
- [API Reference](https://geeks-trident-llc.github.io/parseforge/reference/api/) — every public function/class, by pipeline stage
- [Changelog](https://geeks-trident-llc.github.io/parseforge/changelog/) — what shipped in each release
- [SPEC.md](SPEC.md) — full design plan and open questions
