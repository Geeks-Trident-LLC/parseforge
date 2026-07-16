# ParseForge

`parseforge` is an LLM-driven pipeline that forges, cross-validates, and
promotes [TextFSM](https://github.com/google/textfsm) templates from network
device CLI output — turning a raw `show` command's output into a validated,
production-ready parser.

## How it works

1. **Naming** — an LLM turns a raw CLI command into a canonical, indexed
   `cli-name` (`show interface GE1.1 status` → `show-interface-var1-status`),
   cached locally so a given command is only ever sent to the LLM once.
2. **Sampling** — connect to a device and capture raw command output.
3. **Generation** — send the sample to an LLM and extract a candidate
   TextFSM template.
4. **Validation** — self-validate a candidate against its own sample, then
   cross-validate every candidate for a `cli-name` against every known
   sample to select the best-generalizing one.
5. **Promotion** — the winning candidate is auto-promoted or queued for
   human review, then tracked for drift against new production samples.

Templates move through three storage tiers as they earn trust:
`trials/` (raw, unreviewed attempts) → `integration/` (cross-validated
candidates) → `authoritative/` (approved, in production use).

## Status

This project is an early-stage scaffold. Naming (LLM-backed, with a
local cache) is implemented; sampling, generation, validation, and
promotion are stubbed interfaces waiting on a wired-in LLM client.

## Explore further

- [README](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/README.md) — package layout and local development setup
- [SPEC](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/SPEC.md) — full design plan and open questions
