"""Tests for atomic tool-call preflight and conservative repair."""

from __future__ import annotations

import json

import pytest

from moiryx.errors import ToolCallRepairError
from moiryx.messages import RepairMessage, ToolCall, ToolMessage
from moiryx.tools.definition import build_tool_definition
from moiryx.tools.executor import ToolExecutor
from moiryx.tools.preflight import (
    ToolRepairTracker,
    build_repair_feedback,
    execute_prepared_batch,
    preflight_tool_calls,
)


def _definitions() -> tuple[object, object]:
    def record(value: int) -> str:
        return f"recorded:{value}"

    def label(name: str, prefix: str = "item") -> str:
        return f"{prefix}:{name}"

    return build_tool_definition(record), build_tool_definition(label)


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_invalid_call_blocks_every_tool_before_side_effect() -> None:
    mutations: list[int] = []

    def mutate(value: int) -> str:
        mutations.append(value)
        return "done"

    def inspect_count(count: int) -> int:
        return count

    definitions = (
        build_tool_definition(mutate),
        build_tool_definition(inspect_count),
    )
    result = preflight_tool_calls(
        (
            ToolCall(id="call-1", name="mutate", arguments={"value": 7}),
            ToolCall(
                id="call-2",
                name="inspect_count",
                arguments={"count": "invalid"},
            ),
        ),
        definitions,
    )

    assert result.is_valid is False
    assert result.calls == ()
    assert len(result.issues) == 1
    with pytest.raises(ValueError, match="preflight issues"):
        await execute_prepared_batch(result, ToolExecutor(1))
    assert mutations == []


@pytest.mark.asyncio
async def test_valid_batch_executes_sequentially_and_preserves_identity() -> None:
    order: list[int] = []

    def append(value: int) -> dict[str, int]:
        order.append(value)
        return {"value": value}

    definition = build_tool_definition(append)
    result = preflight_tool_calls(
        (
            ToolCall(id="first", name="append", arguments={"value": 1}),
            ToolCall(id="second", name="append", arguments={"value": 2}),
        ),
        (definition,),
    )

    messages = await execute_prepared_batch(result, ToolExecutor(1))

    assert order == [1, 2]
    assert [(message.tool_call_id, message.name) for message in messages] == [
        ("first", "append"),
        ("second", "append"),
    ]
    assert [json.loads(message.content) for message in messages] == [
        {"value": 1},
        {"value": 2},
    ]


def test_every_invalid_call_is_reported() -> None:
    record, label = _definitions()
    result = preflight_tool_calls(
        (
            ToolCall(id="one", name="record", arguments={}),
            ToolCall(id="two", name="label", arguments={"name": 42}),
        ),
        (record, label),  # type: ignore[arg-type]
    )

    assert result.calls == ()
    assert [issue.call_id for issue in result.issues] == ["one", "two"]
    assert all(issue.kind == "validation" for issue in result.issues)


@pytest.mark.parametrize(
    "call",
    (
        ToolCall(
            id="plain", name=" record ", arguments=None, raw_arguments='{"value":"42"}'
        ),
        ToolCall(
            id="double",
            name="record",
            arguments=None,
            raw_arguments=json.dumps(json.dumps({"value": "42"})),
        ),
        ToolCall(
            id="wrapper",
            name="record",
            arguments={"arguments": {"value": "42"}},
        ),
    ),
)
def test_allowed_repairs_produce_valid_arguments(call: ToolCall) -> None:
    record, _ = _definitions()

    result = preflight_tool_calls((call,), (record,))  # type: ignore[arg-type]

    assert result.is_valid is True
    assert result.calls[0].name == "record"
    assert result.calls[0].arguments.value == 42


def test_arguments_field_is_never_unwrapped_when_declared_by_tool() -> None:
    def consume(arguments: dict[str, int]) -> int:
        return arguments["value"]

    result = preflight_tool_calls(
        (
            ToolCall(
                id="call-1",
                name="consume",
                arguments={"arguments": {"value": 3}},
            ),
        ),
        (build_tool_definition(consume),),
    )

    assert result.is_valid is True
    assert result.calls[0].arguments.arguments == {"value": 3}


@pytest.mark.parametrize(
    "raw_arguments",
    (
        '[{"value": 1}]',
        '"\\"{\\\\\\"value\\\\\\": 1}\\""',
        'prefix {"value": 1} suffix',
    ),
)
def test_non_object_triple_encoded_and_malformed_json_are_not_guessed(
    raw_arguments: str,
) -> None:
    record, _ = _definitions()

    result = preflight_tool_calls(
        (
            ToolCall(
                id="call-1",
                name="record",
                arguments=None,
                raw_arguments=raw_arguments,
                parse_error="provider parse failed",
            ),
        ),
        (record,),  # type: ignore[arg-type]
    )

    assert result.is_valid is False
    assert result.issues[0].kind == "parse"
    assert result.issues[0].raw_arguments == raw_arguments
    assert result.issues[0].parse_error == "provider parse failed"


def test_unknown_fields_and_missing_values_are_not_repaired() -> None:
    record, _ = _definitions()

    extra = preflight_tool_calls(
        (ToolCall(id="extra", name="record", arguments={"value": 1, "x": 2}),),
        (record,),  # type: ignore[arg-type]
    )
    missing = preflight_tool_calls(
        (ToolCall(id="missing", name="record", arguments={}),),
        (record,),  # type: ignore[arg-type]
    )

    assert extra.issues[0].kind == "validation"
    assert missing.issues[0].kind == "validation"


@pytest.mark.acceptance
def test_unknown_tool_is_suggested_but_never_resolved() -> None:
    record, label = _definitions()

    result = preflight_tool_calls(
        (ToolCall(id="call-1", name="records", arguments={"value": 1}),),
        (record, label),  # type: ignore[arg-type]
    )

    assert result.calls == ()
    assert result.issues[0].kind == "unknown_tool"
    assert "Available tools: record, label" in result.issues[0].feedback
    assert "Did you mean 'record'?" in result.issues[0].feedback


def test_validation_feedback_is_concise_and_bound_to_call_id() -> None:
    record, _ = _definitions()
    result = preflight_tool_calls(
        (
            ToolCall(
                id="call-9",
                name="record",
                arguments={"value": "sentinel-secret"},
            ),
        ),
        (record,),  # type: ignore[arg-type]
    )

    feedback = build_repair_feedback(result)

    assert len(feedback) == 1
    assert isinstance(feedback[0], ToolMessage)
    assert feedback[0].tool_call_id == "call-9"
    assert "value" in feedback[0].content
    assert "Expected parameters: value (required)" in feedback[0].content
    assert "sentinel-secret" not in feedback[0].content


def test_missing_call_id_uses_internal_repair_message() -> None:
    record, _ = _definitions()
    result = preflight_tool_calls(
        (ToolCall(id="", name="record", arguments={}),),
        (record,),  # type: ignore[arg-type]
    )

    feedback = build_repair_feedback(result)

    assert len(feedback) == 1
    assert isinstance(feedback[0], RepairMessage)


def test_repeated_invalid_call_consumes_budget_and_exhaustion_has_context() -> None:
    record, _ = _definitions()
    call = ToolCall(
        id="call-1",
        name="record",
        arguments=None,
        raw_arguments='{"value":"bad"}',
    )
    result = preflight_tool_calls((call,), (record,))  # type: ignore[arg-type]
    tracker = ToolRepairTracker(
        2,
        agent_name="reviewer",
        model_alias="strong",
        provider_name="local",
        model_id="vendor/model",
        run_id="run-7",
    )

    tracker.feedback_for(result)
    tracker.feedback_for(result)

    assert tracker.attempts == 2
    assert tracker.fingerprints[0] == tracker.fingerprints[1]
    with pytest.raises(ToolCallRepairError) as captured:
        tracker.feedback_for(result)

    error = captured.value
    assert error.context == {
        "agent": "reviewer",
        "model": "strong",
        "provider": "local",
        "model_id": "vendor/model",
        "run": "run-7",
        "tool": "record",
        "attempts": 2,
        "limit": 2,
    }
    assert error.raw_arguments == '{"value":"bad"}'
    assert error.error_summary is not None
    assert error.error_summary.startswith("Tool call validation failed for 'record'")
    assert "value" in error.error_summary


def test_equivalent_raw_objects_have_the_same_fingerprint() -> None:
    record, _ = _definitions()
    first = preflight_tool_calls(
        (
            ToolCall(
                id="one",
                name="record",
                arguments={"value": "bad", "extra": 1},
            ),
        ),
        (record,),  # type: ignore[arg-type]
    )
    second = preflight_tool_calls(
        (
            ToolCall(
                id="two",
                name="record",
                arguments={"extra": 1, "value": "bad"},
            ),
        ),
        (record,),  # type: ignore[arg-type]
    )

    assert first.fingerprint == second.fingerprint


@pytest.mark.parametrize("limit", (-1, True, 1.5))
def test_repair_limit_must_be_a_non_negative_integer(limit: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        ToolRepairTracker(limit)  # type: ignore[arg-type]
