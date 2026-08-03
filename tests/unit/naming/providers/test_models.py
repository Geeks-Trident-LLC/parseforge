import pytest

from parseforge.naming.providers.models import default_model

PROVIDERS = [
    "anthropic",
    "deepseek",
    "openai",
    "groq",
    "xai",
    "together",
    "fireworks",
    "perplexity",
    "openrouter",
    "moonshot",
    "cerebras",
    "mistral",
    "cohere",
    "gemini",
    "vertexai",
    "bedrock",
    "oci",
]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_default_model_returns_a_non_empty_string(provider: str) -> None:
    model = default_model(provider)
    assert isinstance(model, str)
    assert model
