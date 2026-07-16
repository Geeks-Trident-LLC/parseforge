"""Anthropic-backed RegexBuilder implementation."""

from __future__ import annotations

from anthropic import Anthropic

from ..llm import CliContext, build_prompt
from .models import default_model
from .text import extract_pattern

DEFAULT_MODEL = default_model("anthropic")


class AnthropicRegexBuilder:
    """Builds a cli-name regex pattern by prompting a Claude model.

    The Anthropic client is constructed lazily, on the first actual call —
    not in ``__init__`` — so this can be used as a default RegexBuilder
    without requiring ``ANTHROPIC_API_KEY`` to be set for cache-hit lookups,
    which never reach the LLM at all (see resolver.cli_name).

    API key resolves from the ``api_key`` argument if given, otherwise the
    ``ANTHROPIC_API_KEY`` environment variable (the SDK's own default).
    """

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self._client: Anthropic | None = None

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = (
                Anthropic(api_key=self._api_key) if self._api_key else Anthropic()
            )
        return self._client

    def build_pattern(self, command: str, context: CliContext) -> str:
        prompt = build_prompt(command, context)
        response = self._get_client().messages.create(
            model=self.model,
            # Headroom in case a future/opt-in extended-thinking model burns
            # part of the budget on reasoning before the actual answer — see
            # the deepseek-v4-flash truncation this guards against in
            # providers/deepseek.py.
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return extract_pattern(text)
