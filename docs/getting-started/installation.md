# Installation

## For using the CLI or Python API

```bash
pip install parseforge[anthropic]
```

`pip install parseforge` alone installs no AI-provider SDK at all — every
command that's pure local processing (`canonical`/`readable`/`recognizers`,
`integration`, `promotion`) works with nothing further. Anything that calls
an LLM (`name`, `check --provider`, `run`, `generate-template`, `trial`)
needs the extra for whichever provider it uses:

`anthropic`, `openai`, `deepseek`, `groq`, `xai`, `together`, `fireworks`,
`perplexity`, `openrouter`, `moonshot`, `cerebras`, `mistral`, `cohere`,
`azure`, `gemini`, `vertexai`, `bedrock`, `oci`

`--provider` defaults to `anthropic` wherever it isn't required, so that's
the one most setups need. `pip install parseforge[sampling]` adds Netmiko
for live device sampling. Combine extras as needed:

```bash
pip install parseforge[anthropic,openai,deepseek,groq,xai,together,fireworks,perplexity,openrouter,moonshot,cerebras,mistral,cohere,azure,gemini,vertexai,bedrock,oci,sampling]
```

Four providers don't fit the usual `--api-key`/`--model` shape — see the
[README's naming section](https://github.com/Geeks-Trident-LLC/parseforge/blob/main/README.md#cli)
for what each one needs instead:

| Provider | Needs |
|---|---|
| `azure` | `--endpoint`, `--api-version`, `--deployment` (no fixed model catalog) |
| `vertexai` | `--gcp-project`, `--gcp-location` (no API key — GCP Application Default Credentials) |
| `bedrock` | `--region` (no API key — AWS's own credential chain) |
| `oci` | `--region`, `--compartment-id` (no API key — signs requests against local `~/.oci/config`) |

## For local development

```bash
pip install -e ".[dev,sampling]"
pytest
```

`dev` already includes the `anthropic`, `openai`, `mistralai`, `cohere`,
`azure-ai-inference`, `google-genai`, `boto3`, and `oci` SDKs — tests
exercise all eighteen providers and should never silently skip. Add a
specific `,<provider>` extra explicitly only if installing outside of `dev`.

Linting/formatting/type-checking/docs run through tox instead of extras —
see `tox.ini` (`tox -e lint`/`format`/`typecheck`/`docs`), each installing
its own tools in an isolated env.

### Working on (or testing) a single provider

Cloning the repo to work on one specific naming provider doesn't require
`pip install -e ".[dev]"` and every provider SDK at once — each provider
has its own `requirements/dev-<provider>.txt` that installs `parseforge`
itself, `pytest`/`pytest-cov`, and just that provider's SDK:

```bash
git clone https://github.com/Geeks-Trident-LLC/parseforge.git
cd parseforge
pip install -r requirements/dev-oci.txt
pytest tests/unit/naming/providers/test_oci.py
```

`requirements/requirements-<provider>.txt` is the leaner counterpart — just
`parseforge` plus that provider's SDK, no test tooling — for installs that
don't need to run the test suite; each mirrors the matching
`pyproject.toml` extra exactly (`pip install -r requirements/requirements-oci.txt`
is equivalent to `pip install -e ".[oci]"`).

### Cutting a release

```bash
pip install -e ".[release]"
```

Installs `bump2version` and `build` — see `scripts/release.ps1`.
