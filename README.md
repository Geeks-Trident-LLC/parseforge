# ParseForge

LLM-driven pipeline that forges, cross-validates, and promotes [TextFSM](https://github.com/google/textfsm)
templates from network device CLI output.

Full design plan: [SPEC.md](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/SPEC.md).

## What is ParseForge?

Network devices — routers, switches, firewalls — only speak in plain text:
the output of a `show` command. To use that output in a script, dashboard,
or automation tool, something has to turn it into structured data first.
That "something" is a [TextFSM](https://github.com/google/textfsm)
template: a set of parsing rules for one specific command's output.

ParseForge writes those templates for you. Point it at a device (or a
saved copy of its output) and an AI provider of your choice, and it
produces a template, checks that the template actually parses the sample
it was built from, and tracks the result so you can see exactly how much
it's been tested before you trust it in production.

## Why do you need ParseForge?

Every network automation project eventually hits the same wall: someone
has to write and maintain a parser for every command's output, by hand,
in regex. It's slow, it's easy to get subtly wrong, and it only gets
worse as you add more device types, vendors, and firmware versions —
each with its own quirks in how the same command's output is formatted.

ParseForge replaces that manual work with a repeatable pipeline: an AI
drafts the parser, ParseForge verifies it against real output before
trusting it, and only well-tested results get promoted to production use
automatically — anything uncertain is queued for a quick human look
instead of shipped blind. If your team does network automation and needs
structured data out of CLI output, ParseForge is the part that used to be
tedious, made fast and safe instead.

## Features

- **Nothing ships unreviewed.** Every AI-generated template starts as
  unproven evidence. Once it's been tested enough times with consistent
  results, it's promoted automatically; anything less certain waits for a
  person to check it.
- **Learns a command once, reuses it forever.** The first time a command
  runs, ParseForge asks the AI to name it; every time after that, it's
  a free, instant lookup — no repeat AI calls, no repeat cost.
- **Checks its own work.** Every generated template is tested against the
  real output it was built from before it's ever counted as a pass.
- **Notices when things change.** If a device's output format changes
  later, ParseForge catches it and automatically kicks off a retest,
  instead of quietly parsing it wrong.
- **Use it your way.** A command-line tool for quick, ad hoc use, or a
  Python library for wiring straight into your own automation — same
  functionality either way.

## Supported providers

Eighteen AI providers behind one common interface — mix and match, or use
two different ones in the same run:

Anthropic, OpenAI, DeepSeek, Groq, xAI, Together, Fireworks, Perplexity,
OpenRouter, Moonshot, Cerebras, Mistral, Cohere, Azure OpenAI, Google
Gemini, Google Vertex AI, Amazon Bedrock, and Oracle Cloud Infrastructure
(OCI) — including the four with non-standard authentication (Azure
deployment names, GCP Application Default Credentials, AWS's own
credential chain, OCI request-signing), handled transparently. See
[Providers](https://geeks-trident-llc.github.io/parseforge/guides/providers/)
for each one's install extra, auth requirements, and default model.

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
- [SPEC.md](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/SPEC.md) — full design plan and open questions
