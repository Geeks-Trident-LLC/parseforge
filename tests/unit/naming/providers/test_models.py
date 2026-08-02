import pytest

from parseforge.naming.providers.models import (
    default_model,
    deprecated_models,
    supported_models,
)

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
]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_default_model_is_in_supported_list(provider: str) -> None:
    assert default_model(provider) in supported_models(provider)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_default_model_is_not_deprecated(provider: str) -> None:
    assert default_model(provider) not in deprecated_models(provider)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_deprecated_models_defaults_to_empty_list(provider: str) -> None:
    assert deprecated_models(provider) == []
