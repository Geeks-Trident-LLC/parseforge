"""DeepSeek-backed RegexBuilder implementation.

DeepSeek's API mirrors OpenAI's chat.completions surface (same request/
response format), so this uses the `openai` SDK pointed at DeepSeek's
base URL rather than a dedicated DeepSeek client.
"""

from __future__ import annotations

import os

from openai import OpenAI

from ..llm import CliContext, build_prompt
from .models import default_model
from .text import extract_pattern

DEFAULT_MODEL = default_model("deepseek")

_BASE_URL = "https://api.deepseek.com"


class DeepSeekRegexBuilder:
    """Builds a cli-name regex pattern by prompting a DeepSeek model.

    The client is constructed lazily, on the first actual call — not in
    ``__init__`` — so this can be used as a default RegexBuilder without
    requiring ``DEEPSEEK_API_KEY`` to be set for cache-hit lookups, which
    never reach the LLM at all (see resolver.cli_name).

    API key resolves from the ``api_key`` argument if given, otherwise the
    ``DEEPSEEK_API_KEY`` environment variable (unlike Anthropic/OpenAI's
    SDKs, the ``openai`` package has no built-in notion of DeepSeek's key,
    so this is resolved explicitly rather than left to the SDK).
    """

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            api_key = self._api_key or os.environ.get("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "no DeepSeek API key — pass api_key or set DEEPSEEK_API_KEY"
                )
            self._client = OpenAI(api_key=api_key, base_url=_BASE_URL)
        return self._client

    def build_pattern(self, command: str, context: CliContext) -> str:
        prompt = build_prompt(command, context)
        response = self._get_client().chat.completions.create(
            model=self.model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        return extract_pattern(text)
