"""Tests for tool-result serialization and explicit truncation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, TypeAdapter

from moiryx.errors import ToolExecutionError
from moiryx.tools.serialization import build_tool_message, serialize_tool_result


class ResultModel(BaseModel):
    value: int


@dataclass
class DataclassResult:
    name: str
    count: int


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("plain text", "plain text"),
        (None, "null"),
        (True, "true"),
        (3, "3"),
        ([1, "two"], '[1,"two"]'),
        ({"valid": True}, '{"valid":true}'),
        (ResultModel(value=7), '{"value":7}'),
        (DataclassResult(name="batch", count=2), '{"name":"batch","count":2}'),
    ),
)
def test_supported_results_are_serialized(value: object, expected: str) -> None:
    assert serialize_tool_result(value) == expected


def test_return_adapter_serializes_annotated_types() -> None:
    value = datetime(2026, 9, 13, 12, 30, tzinfo=UTC)

    serialized = serialize_tool_result(value, return_adapter=TypeAdapter(datetime))

    assert serialized == "2026-09-13T12:30:00Z"


def test_build_tool_message_preserves_call_identity() -> None:
    message = build_tool_message(
        "call-7",
        "lookup",
        {"items": [1, 2]},
    )

    assert message.tool_call_id == "call-7"
    assert message.name == "lookup"
    assert json.loads(message.content) == {"items": [1, 2]}


def test_oversized_output_has_visible_marker_with_configured_limit() -> None:
    serialized = serialize_tool_result("abcdefghij", max_chars=5)

    assert serialized.startswith("abcde...[TRUNCATED BY MOIRYX:")
    assert "exceeded 5 chars" in serialized


def test_unsupported_result_has_concrete_error() -> None:
    with pytest.raises(ToolExecutionError, match="could not be serialized"):
        serialize_tool_result(object())


def test_message_serialization_error_includes_tool_context() -> None:
    with pytest.raises(ToolExecutionError, match="tool=lookup"):
        build_tool_message("call-8", "lookup", object())


@pytest.mark.parametrize("limit", (0, -1, True, 1.5))
def test_output_limit_must_be_a_positive_integer(limit: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        serialize_tool_result("value", max_chars=limit)  # type: ignore[arg-type]
