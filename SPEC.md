# Network CLI → TextFSM Template Generator — Project Plan & Requirements

## 1. Project & Repo Naming

| Candidate | Repo name (kebab-case) | Rationale |
|---|---|---|
| **ParseForge** | `parseforge` | Short, memorable, clearly about forging parsers. Available-sounding, no CLI/network jargon lock-in if you expand beyond Cisco later. |
| **CLIFsm** | `cli-fsm-forge` | Literal — CLI + FSM (finite state machine, what TextFSM templates are). Good for discoverability if someone searches "textfsm" + "cli". |
| **ShowParse AI** | `showparse-ai` | Leans into the fact that almost every input is a `show` command. Very descriptive, less generic. |
| **NetFSM** | `netfsm` | Shortest option. Good if this becomes a pip-installable library/CLI tool people type often. |

**Recommendation:** `parseforge` as the project name, `parseforge` (or `parseforge-textfsm`) as the repo name. It reads well as a CLI tool name (`parseforge run ...`), isn't locked to Cisco/TextFSM specifically if you extend to other vendors or output formats (e.g., ntc-templates-style YAML, TTP, or Genie parsers) later, and is easy to say out loud.

If you want to keep `textfsm-ai` since that's the term you're already using internally/in docs, that's a perfectly reasonable literal alternative — just know it reads as "TextFSM, but AI" rather than as a product name, which is fine for an internal tool but less distinctive if this is ever open-sourced.

---

## 2. CLI-to-Name Translation

**Rule:** Tokenize the full command string. Classify each token as **literal** (fixed across all invocations of this command type) or **variable** (an identifier — interface name, VLAN ID, IP, hostname, etc.).

**Naming convention — always index variables, even when there's only one:**

```
show version                         → show-version
show interface GE1.1 status          → show-interface-var1-status
show interface GE1.1 counters        → show-interface-var1-counters
show ip route 10.0.0.0                → show-ip-route-var1
show bgp neighbors 10.1.1.1 advertised-routes
                                       → show-bgp-neighbors-var1-advertised-routes
```

**Why always number, even for a single variable (`var1` not `var`):**
A naming function that omits the index for single-variable commands has to *already know* the final variable count before naming — but that can change: a newer OS version might add an optional second argument to the same command family, or you might discover a command has two variable slots you didn't notice on first sample. Indexing consistently means:
- The name-generation code is a pure, stateless function of token position — no lookahead needed.
- No silent renames/migrations later if a command turns out to have more variables than expected.
- Multi-variable commands (2+) stay unambiguous by construction — `var1`, `var2` in left-to-right order of appearance.

This differs slightly from the older convention used in the `ntc-templates` community library (which just drops variable tokens entirely rather than placeholding them — e.g. `cisco_ios_show_interfaces.textfsm` regardless of interface name). That works for them because their catalog is hand-curated and collisions are manually resolved. Since your pipeline is LLM-driven and needs to run unattended, explicit indexed placeholders are safer and self-documenting.

**Edge case — literal tokens that look variable-ish:** keywords like `brief`, `status`, `detail`, `counters`, `summary` are still literal (they're fixed sub-command keywords, not user-supplied values) and stay as literal tokens in the name.

---

## 3. Storage Layout — Three-Tier Promotion

This mirrors the candidate → staging → production pattern used for ML model registries, applied to templates: **trials** (raw, unreviewed attempts) → **integration** (cross-validated candidates, pending approval) → **authoritative** (approved, in production use, drift-monitored).

Shared path prefix under all three tiers:
```
<vendor>/<device-family>/<os>/<cli-name>/
```
e.g. `cisco/catalyst9200/ios-xe/show-interface-var1-status/`

Note: use `ios-xe` / `nx-os` (hyphenated) rather than `xe` / `ios` alone once multiple Cisco OS families share the tree — `xe` alone is ambiguous without the `ios-` prefix once IOS classic, IOS XE, and IOS XR all live under `cisco/`.

Deliberately no `<version>` segment in the path: a cli-name's output structure usually doesn't change across minor OS versions, and when it legitimately does, that's exactly the variance §5 step 8's group clustering is built to catch — lumping versions together under one path gives more evidence per group instead of silently fragmenting it across per-version directories. The OS version a trial was sampled from is recorded per trial instead, in that trial's `summary.json` (`command_info.version`).

### 3.1 `trials/`

```
trials/<vendor>/<family>/<os>/<cli-name>/
  <yyyymmdd-HHMMSS-shortid>/
    input.txt
    raw-llm-response.txt
    usage.txt
    raw-template
    template.textfsm
    readable-dsl.txt
    recognizers.txt
    llm-records.json
    records.json
    debug.txt
    status.txt
```
Keep the timestamp+shortid directories (not `result1..N`) — chronological ordering and collision-safety in batch mode come for free, and sequential numbers throw both away.

| File | Purpose |
|---|---|
| `input.txt` | Raw CLI output sample fed to the LLM |
| `raw-llm-response.txt` | Full, unprocessed LLM response |
| `usage.txt` | Token counts / cost metadata for that call |
| `raw-template` | Template as extracted from the LLM response, pre-cleanup |
| `template.textfsm` | Cleaned TextFSM template candidate (`.textfsm` extension — recognized by TextFSM tooling/linters, unlike `textfsm.template`) |
| `readable-dsl.txt` | Human-readable description of what the template captures |
| `recognizers.txt` | Heuristics/signatures for detecting this output type at runtime |
| `llm-records.json` | Structured record of the LLM interaction (prompt, model, params, timestamps) |
| `records.json` | Result of running this trial's `template.textfsm` against its own `input.txt` |
| `debug.txt` | Parse errors, warnings, retry attempts |
| `status.txt` | `passed`/`failed`, `llm-duration-ms`, `pipeline-duration-ms`, error summary |

### 3.2 `integration/` (no human review yet)

```
integration/<vendor>/<family>/<os>/<cli-name>/
  common-result/
    template.textfsm       ← the winning candidate, copied from trials/
    selection-report.json  ← which trials were considered, why this one won
    artifact/               ← supporting evidence (see below)
```

**How "common" gets chosen — don't just self-validate:** test *every* candidate `template.textfsm` from `trials/<cli-name>/` against *every* `input.txt` collected for that `cli-name`, not only the sample it was generated from. Promote whichever template parses the largest share of all known samples correctly. A template that only works against its own source sample is exactly the overfit case integration should catch. If you generate multiple candidates from the same input (repeated LLM calls), a structure that recurs across generations is additional evidence of stability — worth folding into the score, not just accuracy alone.

`selection-report.json` should record: which trial run IDs were candidates, the cross-validation match rate for each, which samples the winner failed on (if any), and the score that made it win. This is what a human reviewer actually reads — the raw template alone doesn't convey robustness.

`artifact/` holds whatever a reviewer needs to judge the result without re-running the pipeline: the aggregated `records.json` outputs across all cross-validated samples, and a diff/summary of any samples where the winning template didn't fully match.

### 3.3 `authoritative/` (approved via human review, or confidence-gated auto-promotion)

```
authoritative/<vendor>/<family>/<os>/<cli-name>/
  template.textfsm             ← current approved template (the primary variant)
  template-v2.textfsm          ← an additional simultaneously-valid variant (§6), if any
  template-v2-<suffix>.textfsm ← a USER_REVIEWED snapshot of that variant, kept alongside its current version
  recognizers.txt              ← recognizer signature, one per template, same suffix rule
  data/
    sample.txt, records.json   ← the sample + parsed output behind each template, same suffix rule
  golden.hash                  ← sha256 of the most recently promoted template, regardless of variant
  artifact.json                ← who/when/mode/match-rate/source of the most recent promotion
  drift-log.json               ← rolling match rate over time per variant, against live production samples
  history/
    template-<yyyymmdd-HHMMSS>-<shortid>.textfsm   ← prior content, archived whenever a promotion overwrites it with something different

authoritative/
  authoritative-log.json       ← project-wide, append-only: every promotion event ever, across every cli-name
  authoritative-summary.json   ← project-wide snapshot of the most recent promotion run
```

No per-variant subdirectory — every simultaneously-valid template for a `cli-name` (§6, hardware/firmware variance) lives directly in this one flat directory, distinguished by filename. The first-discovered variant owns the unsuffixed "current version" names; each additional variant owns a stable, permanent `template-v2.textfsm`, `template-v3.textfsm`, ... derived from its own group id and never renumbered. `golden.hash` and `artifact.json` are the one exception to per-variant filenames: both are singular and unsuffixed, always reflecting whichever promotion happened most recently regardless of which variant triggered it.

Promotion defaults to human review, but can be confidence-gated per variant: if a variant's match rate — against only the trials that actually passed, not diluted by raw generation failures — is at or near 100% with enough samples, auto-promote it; otherwise it's queued for review. Two modes cover this: **AUTO_PROMOTED** walks every case and promotes every qualifying variant unsuffixed; **USER_REVIEWED** is scoped to caller-reviewed `(case, suffix)` requests, writing a suffixed snapshot alongside whatever that variant's current auto-promoted files already are, never replacing them. This isn't a replacement for review — it's a filter that keeps the easy, unambiguous cases from waiting on a person while still requiring a human on anything uncertain.

**Drift detection** runs an authoritative template against new production samples on an ongoing basis, tracking a rolling match rate per variant in that cli-name's `drift-log.json`. When the rate drops below threshold, that failing sample is written into `trials/.../<cli-name>/` as a new run, which re-enters the pipeline at §5 step 4 and works its way back through `integration/` to a possible new `authoritative/` version — closing the loop rather than treating drift as a one-off alert.

---

## 4. Execution Modes

**Mode 1 — Batch (gather-then-generate):**
- Pro: LLM can be shown patterns across multiple samples of the *same* command at once (e.g., three different interface states) in one shot, likely improving template robustness on the first try.
- Con: Slower feedback loop — you don't know command #3 has a connectivity problem until after collecting #1–#10.

**Mode 2 — Loop (sample → generate, per command):**
- Pro: Fails fast and isolates problems per-command; simpler to debug; easier to parallelize across commands.
- Con: Each template is generated from a single sample unless you explicitly loop multiple times per command and merge.

**Recommendation:** Build Mode 2 first as the MVP — it's the simpler pipeline and gives you per-command `status.txt` results immediately. Add Mode 1 as a config flag afterward that changes only the *sampling* stage (collect N samples per command before invoking the LLM) — the generation, storage, and validation stages stay identical between modes if you design sampling as a separable stage up front.

---

## 5. Pipeline Steps

1. **Input intake** — device OS/version/family, auth, command list, mode selection.
2. **Name generation** — tokenize each command → canonical `cli-name` per §2.
3. **Path resolution** — compute `<vendor>/<device-family>/<os>/<cli-name>/` per §3.
4. **Sampling** — connect (Netmiko/similar), run command(s), capture raw output → `trials/.../<run-id>/input.txt`.
5. **Generation** — send `input.txt` (+ prior context if Mode 1) to LLM → `raw-llm-response.txt`, `usage.txt`.
6. **Extraction & cleanup** — pull template from response → `raw-template` → cleaned `template.textfsm`.
7. **Self-validation** — run `template.textfsm` against its own `input.txt` → `records.json`; capture errors → `debug.txt`; write trial `status.txt`.
8. **Integration selection** — cross-validate every candidate `template.textfsm` in `trials/.../<cli-name>/` against every known `input.txt` for that `cli-name`; promote the best-scoring one to `integration/.../common-result/`, writing `selection-report.json`.
9. **Authoritative promotion** — auto-promote if the winning candidate clears the confidence threshold across all known samples; otherwise queue for human review. On approval, copy to `authoritative/.../template.textfsm` (or `template-v2.textfsm`, ... for an additional variant), archive the prior content to `history/` if it differs, and write `golden.hash`, `artifact.json`, and `authoritative-log.json`.
10. **Drift monitoring** — continuously run the authoritative template against new production samples, logging match rate to `drift-log.json`. On breach, feed the failing sample back into `trials/` (→ step 4) to generate a replacement candidate.
11. **Repeat/loop or batch-complete** depending on mode.

---

## 6. Design Notes: Is Three-Tier Enough?

**Yes, for the promotion pipeline itself.** `trials → integration → authoritative` covers the full lifecycle a template needs to go through to earn trust: generate, cross-validate, approve. Adding a fourth *promotion* tier (e.g. a separate "staging" between integration and authoritative) wouldn't buy you anything distinct — integration already *is* the staging step, since nothing in it is live yet.

Where a fourth tier is tempting but better handled as **metadata instead of a new directory layer:**

- **Quarantine / stale-but-still-serving:** when drift is detected, the authoritative template is still the one in production use — you don't want to yank it out mid-flight while a replacement works its way through the pipeline. Rather than a new top-level tier, this is a `status` field in `drift-log.json` (`ok` / `drifting` / `superseded`) on the existing authoritative entry. The template keeps serving; the status just flags that a replacement is in flight.
- **Archived / deprecated (EOL device-OS combos):** for template families you no longer actively maintain (e.g. an OS version taken out of production fleet-wide), this is also a status flag rather than a directory move — `history/` already retains every prior version, so "archived" just means `authoritative-log.json` stops getting new entries for that cli-name, not that files need to relocate.
- **Multiple simultaneously-valid templates for one `cli-name`:** if a command's output legitimately varies by hardware config (e.g. a chassis with vs. without an optional module) rather than by drift, that's not a tier problem — it's a case for storing *multiple* authoritative templates under the same `cli-name` path with distinct `recognizers.txt` signatures, and letting runtime dispatch pick the right one. Worth flagging now so `recognizers.txt` is designed to support one-of-many matching from the start rather than assuming exactly one template per `cli-name`.

**Bottom line:** keep the three directories; push the "in-between" states (drifting-but-live, archived, multi-variant) into metadata/status fields on the existing tiers. Adding more top-level directories per edge case leads to directory sprawl without adding real distinctions in *how* a template is used.

---

## 7. Open Questions for Next Iteration

- Do you want a **registry/index file** (e.g. `catalog.json`) at the repo root listing every `<vendor>/<family>/<os>/<cli-name>` combination that exists, plus its authoritative status, for fast lookup without walking the filesystem?
- What **confidence threshold** (match-rate %, sample count minimum) should gate auto-promotion vs. human review in step 9 — worth making this configurable per-project rather than hardcoded?
- Should `recognizers.txt` support **one-of-many matching** from day one (per the multi-variant note in §6), or is that a v2 concern?
- What's the **LLM provider/model** for generation — worth pinning per-project so `usage.txt` costs are comparable across runs?
