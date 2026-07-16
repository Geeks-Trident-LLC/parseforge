# ParseForge

LLM-driven pipeline that forges, cross-validates, and promotes [TextFSM](https://github.com/google/textfsm)
templates from network device CLI output.

Full design plan: [SPEC.md](SPEC.md).

## Layout

```
parseforge/
  naming.py       CLI command -> canonical cli-name (SPEC §2)
  paths.py        trials/integration/authoritative path resolution (SPEC §3)
  sampling.py     device connection + command capture (SPEC §5 step 4)
  generation.py   LLM call + template extraction (SPEC §5 steps 5-6)
  validation.py   self-validation + cross-validation scoring (SPEC §5 steps 7-8)
  promotion.py    authoritative promotion gate + drift status (SPEC §3.3, §5 steps 9-10)
  pipeline.py     orchestrates the above; Mode LOOP (MVP) vs Mode BATCH (SPEC §4)
  cli/            `parseforge` command-line entry point

store/            runtime template tree: trials/ -> integration/ -> authoritative/
                  (generated at runtime, not checked in — see .gitignore)
```

`naming.py` and `paths.py` are implemented and tested. `sampling.py`, `generation.py`,
`validation.py`, `promotion.py`, and `pipeline.py` are stub interfaces — the SPEC.md
section cited in each docstring is the next thing to implement.

## Development

```
pip install -e ".[dev,sampling]"
pytest
```

## CLI

```
parseforge name show interface GE1.1 status
# -> show-interface-var1-status
```
