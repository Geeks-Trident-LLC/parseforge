import pytest

from parseforge.naming.llm import CliContext
from parseforge.naming.providers.deepseek import DEFAULT_MODEL, DeepSeekRegexBuilder

CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeCompletions:
    def __init__(self, reply_text: str) -> None:
        self.reply_text = reply_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Resp", (), {"choices": [_FakeChoice(self.reply_text)]})()


class _FakeChat:
    def __init__(self, reply_text: str) -> None:
        self.completions = _FakeCompletions(reply_text)


class _FakeOpenAI:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key
        self.base_url = base_url
        self.chat = _FakeChat(r"show\s+version")


def test_build_pattern_calls_client_and_extracts_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-key")
    fake = _FakeOpenAI()
    monkeypatch.setattr(
        "parseforge.naming.providers.deepseek.OpenAI", lambda **kw: fake
    )

    builder = DeepSeekRegexBuilder()
    pattern = builder.build_pattern("show version", CONTEXT)

    assert pattern == r"show\s+version"
    assert len(fake.chat.completions.calls) == 1
    call = fake.chat.completions.calls[0]
    assert call["model"] == DEFAULT_MODEL
    assert "show version" in call["messages"][0]["content"]


def test_client_is_constructed_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instantiating the builder must not require an API key or touch the network —
    a cache-hit lookup never calls build_pattern at all (see resolver.cli_name)."""

    def _boom(**kwargs):
        raise AssertionError("OpenAI() should not be constructed eagerly")

    monkeypatch.setattr("parseforge.naming.providers.deepseek.OpenAI", _boom)

    DeepSeekRegexBuilder()  # must not raise


def test_api_key_argument_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    captured = {}

    def _fake_ctor(**kwargs):
        captured.update(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("parseforge.naming.providers.deepseek.OpenAI", _fake_ctor)

    builder = DeepSeekRegexBuilder(api_key="sk-test-123")
    builder.build_pattern("show version", CONTEXT)

    assert captured == {
        "api_key": "sk-test-123",
        "base_url": "https://api.deepseek.com",
    }


def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    builder = DeepSeekRegexBuilder()

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        builder.build_pattern("show version", CONTEXT)
