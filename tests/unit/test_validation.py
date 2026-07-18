from __future__ import annotations

from parseforge.validation import parse

_WORKING_TEMPLATE = "Value LINE (.+)\n\nStart\n  ^${LINE} -> Record\n"
_BROKEN_TEMPLATE = "this is not a valid textfsm template !!!"


def test_parse_working_template_returns_records() -> None:
    result = parse(_WORKING_TEMPLATE, "hello world\ngoodbye world\n")

    assert result.passed is True
    assert result.errors == []
    assert result.records == [
        {"LINE": "hello world"},
        {"LINE": "goodbye world"},
    ]


def test_parse_broken_template_returns_errors() -> None:
    result = parse(_BROKEN_TEMPLATE, "hello world\n")

    assert result.passed is False
    assert result.errors != []
    assert result.records == []


def test_parse_template_with_no_matching_lines_returns_empty_records() -> None:
    result = parse(_WORKING_TEMPLATE, "")

    assert result.passed is True
    assert result.records == []
