# Providers

`parseforge` speaks to eighteen LLM providers through a common interface
(`RegexBuilder` for naming, and the same provider name/model/api-key shape
for generation). Install the extra for whichever one you use — see
[Installation](../getting-started/installation.md).

## At a glance

| Provider | Extra | Auth | Default model |
|---|---|---|---|
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | `claude-haiku-4-5-20251001` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-5.4-mini` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-v4-flash` |
| Groq | `groq` | `GROQ_API_KEY` | `llama-3.1-8b-instant` |
| xAI | `xai` | `XAI_API_KEY` | `grok-3-mini` |
| Together | `together` | `TOGETHER_API_KEY` | `meta-llama/Llama-3.1-8B-Instruct-Turbo` |
| Fireworks | `fireworks` | `FIREWORKS_API_KEY` | `accounts/fireworks/models/llama-v3p1-8b-instruct` |
| Perplexity | `perplexity` | `PERPLEXITY_API_KEY` | `sonar` |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` | `google/gemini-2.5-flash-lite` |
| Moonshot | `moonshot` | `MOONSHOT_API_KEY` | `moonshot-v1-8k` |
| Cerebras | `cerebras` | `CEREBRAS_API_KEY` | `llama3.1-8b` |
| Mistral | `mistral` | `MISTRAL_API_KEY` | `mistral-small-latest` |
| Cohere | `cohere` | `COHERE_API_KEY` | `command-light` |
| Gemini | `gemini` | `GEMINI_API_KEY` | `gemini-2.5-flash` |
| Azure OpenAI | `azure` | see [below](#azure-openai) | *(no fixed catalog — deployment name instead)* |
| Vertex AI | `vertexai` | see [below](#vertex-ai) | `gemini-2.5-flash` |
| Amazon Bedrock | `bedrock` | see [below](#amazon-bedrock) | `anthropic.claude-haiku-4-5-v1:0` |
| Oracle Cloud (OCI) | `oci` | see [below](#oracle-cloud-infrastructure-oci) | `meta.llama-3.3-70b-instruct` |

`--api-key`/`api_key=` always falls back to that provider's own env var —
only needed on a naming cache miss, since a cache hit never touches the
LLM at all. `--model`/`model=` defaults to the table above if omitted.

## Non-standard auth providers

Fourteen providers fit the plain `--api-key`/`--model` shape. Four don't:

### Azure OpenAI

No public `base_url` (it's your own Azure resource) and no fixed model
catalog (an account-specific *deployment* name replaces it):

```bash
parseforge name --provider azure --api-key $AZURE_API_KEY \
  --endpoint https://my-resource.openai.azure.com \
  --deployment my-gpt4-deployment \
  show version
```

| Flag | Env var fallback |
|---|---|
| `--api-key` | `AZURE_API_KEY` |
| `--endpoint` | `AZURE_ENDPOINT` |
| `--api-version` | `AZURE_API_VERSION` |
| `--deployment` | `AZURE_DEPLOYMENT` (replaces `--model`) |

### Vertex AI

No API key at all — authenticates through GCP's own Application Default
Credentials — and needs a project and region instead:

```bash
parseforge name --provider vertexai \
  --gcp-project my-project --gcp-location us-central1 \
  show version
```

| Flag | Env var fallback |
|---|---|
| `--gcp-project` | `VERTEXAI_PROJECT` |
| `--gcp-location` | `VERTEXAI_REGION` |

Serves the same Gemini model catalog as the native Gemini provider above,
just through GCP's separate enterprise billing.

### Amazon Bedrock

No API key — authenticates via AWS's own credential chain (env vars,
`~/.aws/credentials`, or an IAM role) — and only needs a region:

```bash
parseforge name --provider bedrock --region us-east-1 show version
```

| Flag | Env var fallback |
|---|---|
| `--region` | `BEDROCK_REGION`, then `BEDROCK_DEFAULT_REGION` |

### Oracle Cloud Infrastructure (OCI)

No API key — signs each request cryptographically against local
credentials in `~/.oci/config` (DEFAULT profile) — and needs both a
region and a compartment ID (the OCID of the compartment/tenancy to bill
and scope requests to):

```bash
parseforge name --provider oci \
  --region us-ashburn-1 --compartment-id ocid1.compartment.oc1..xxxx \
  show version
```

| Flag | Env var fallback |
|---|---|
| `--region` | `OCI_REGION`, then whatever region is already set in `~/.oci/config` |
| `--compartment-id` | `OCI_COMPARTMENT_ID` |

## Naming vs. generation providers

`run`/`trial` split naming and generation into separate provider configs
(`--naming-*` vs. plain `--*`/generation flags) — they default to the same
provider, but you can point them at two different ones, e.g. a cheap fast
model for naming (cached after the first call, so cost matters less) and a
stronger model for generation. Every flag above has a `--naming-`
equivalent. See the [CLI Guide](cli.md#run) for the full flag list.
