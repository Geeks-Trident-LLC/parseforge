import pytest

from parseforge.naming.prompts import load_prompt_template


def test_load_prompt_template_returns_cli_name_regex_template() -> None:
    template = load_prompt_template("cli_name_regex")
    assert "{command}" in template
    assert "{vendor}" in template
    assert "{family}" in template
    assert "{os}" in template
    assert "{version}" in template


def test_load_prompt_template_raises_on_unknown_name() -> None:
    with pytest.raises(KeyError):
        load_prompt_template("does-not-exist")
