from parseforge.naming.llm import CliContext, build_prompt

CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


def test_build_prompt_includes_command_and_context() -> None:
    prompt = build_prompt("show version", CONTEXT)
    assert "show version" in prompt
    assert "cisco" in prompt
    assert "catalyst9200" in prompt
    assert "ios-xe" in prompt
    assert "17.9.1" in prompt


def test_build_prompt_isolates_command_from_context() -> None:
    """Regression guard: an earlier prompt phrased the command and device
    context as one sentence ('This is CLI "{command}" of {vendor} {family}
    {os} version {version}.'), which caused a real LLM to build a regex for
    the whole sentence instead of just the command — treating "cisco" as a
    variable and hallucinating the OS/version into the match target. The
    command must appear in its own clearly delimited section, and the
    prompt must explicitly forbid folding the context into the regex.
    """
    prompt = build_prompt("show version", CONTEXT)

    assert "COMMAND TO CONVERT" in prompt
    command_section = prompt.split("COMMAND TO CONVERT")[1]
    # The device context values must not appear anywhere after the
    # command-to-convert marker — i.e. not bundled alongside the command.
    context_section = prompt.split("COMMAND TO CONVERT")[0]
    for value in (CONTEXT.vendor, CONTEXT.family, CONTEXT.os, CONTEXT.version):
        assert value in context_section
        assert value not in command_section

    assert "do not include" in prompt.lower() or "never" in prompt.lower()
