# ParseForge

`parseforge` is an LLM-driven pipeline that forges, cross-validates, and
promotes [TextFSM](https://github.com/google/textfsm) templates from network
device CLI output — turning a raw `show` command's output into a validated,
production-ready parser.

New here? Start with [Installation](getting-started/installation.md), then
[Quickstart](getting-started/quickstart.md).

## How it works

1. **Naming** — an LLM turns a raw CLI command into a canonical, indexed
   `cli-name` (`show interface GE1.1 status` → `show-interface-var1-status`),
   cached locally so a given command is only ever sent to the LLM once.
2. **Sampling** — connect to a device and capture raw command output.
3. **Generation** — send the sample to an LLM and extract a candidate
   TextFSM template; self-validate it against its own sample.
4. **Integration** — cluster every passed trial for a `cli-name` by the
   output-schema its parsed records actually have, not by exact template
   text. A command's output can legitimately vary by hardware/firmware, so
   distinct schemas become separate, independently-tracked groups instead of
   one hand-picked "winner" — each group's match rate against every known
   sample is what promotion actually gates on.
5. **Promotion** — each group that clears its match-rate/sample-count gate
   is auto-promoted; everything else is queued for human review. A
   human-reviewed promotion is recorded as a named snapshot alongside
   whatever's currently live, never silently overwriting it.
6. **Drift monitoring** — an authoritative template is periodically checked
   against new production samples. A failing sample gets fed back into the
   pipeline as a new trial, closing the loop instead of just logging an
   alert.

Templates move through three storage tiers as they earn trust:
`trials/` (raw, unreviewed attempts) → `integration/` (cross-validated
evidence, grouped by output schema) → `authoritative/` (approved, in
production use, drift-monitored).

## Status

Early beta: the full pipeline — naming, sampling, generation, self-validation,
integration clustering, promotion (auto and human-reviewed), and drift
monitoring — is implemented, tested, and wired into the CLI. A few things are
intentionally not there yet:

- Human-reviewed promotion (`USER_REVIEWED`) has a library entry point but no
  CLI surface — deferred until real cases show what its config shape should
  look like, rather than guessing ahead of need.
- Batch sampling mode (collect several samples per command before
  generating) is designed in
  [SPEC.md](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/SPEC.md)
  §4 but not built; the simpler per-command loop mode is the only one
  implemented.
- Only one sampling connector (Netmiko/SSH) exists today; the CLI's
  `--connector` registry is built to hold more without a redesign.

## Explore further

- [Installation](getting-started/installation.md) — pip extras, dev setup, per-provider requirements files
- [Quickstart](getting-started/quickstart.md) — naming, checks, one-shot generation, and the full trial → integration → promotion workflow
- [README](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/README.md) — package layout, the full CLI reference, and the Python API
- [SPEC](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/SPEC.md) — full design plan and open questions
