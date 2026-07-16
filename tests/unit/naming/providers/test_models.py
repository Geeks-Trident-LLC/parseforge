from parseforge.naming.providers.models import (
    default_model,
    deprecated_models,
    supported_models,
)


def test_default_model_is_in_supported_list() -> None:
    assert default_model("anthropic") in supported_models("anthropic")


def test_default_model_is_not_deprecated() -> None:
    assert default_model("anthropic") not in deprecated_models("anthropic")


def test_deprecated_models_defaults_to_empty_list() -> None:
    assert deprecated_models("anthropic") == []
