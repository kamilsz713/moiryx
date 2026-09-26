"""Tests for the public runtime event protocol."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

import pytest
from pydantic import BaseModel

from moiryx.agent_spec import AgentSpec
from moiryx.config import RuntimeConfig
from moiryx.events import (
    AgentFinished,
    AgentStarted,
    ToolFinished,
    ToolStarted,
    UsageEvent,
    collect_events,
    emit_event,
    event_sink,
    event_to_dict,
    run_scope,
)
from moiryx.messages import AssistantMessage, ToolCall, UserMessage
from moiryx.model_registry import ResolvedModel
from moiryx.models import GenerationOptions, ModelResponse, Usage
from moiryx.providers import ScriptedFakeProvider
from moiryx.runtime import execute_text_agent
from moiryx.tools.definition import build_tool_definition


def _spec() -> AgentSpec:
    return AgentSpec(
        name="events",
        model_alias="strong",
        instructions="Report events.",
        tool_names=(),
        output_model=None,
        max_steps=3,
        generation=GenerationOptions(),
        source_path=Path("events.md"),
    )


def _model() -> ResolvedModel:
    return ResolvedModel(
        alias="strong",
        provider="local",
        model="vendor/model",
        generation=GenerationOptions(),
        provider_options=MappingProxyType({}),
    )


@pytest.mark.asyncio
async def test_collect_events_binds_a_synchronous_context() -> None:
    event = UsageEvent(run_id="run-1", total_tokens=3)

    with collect_events() as events:
        await emit_event(event)

    assert events == [event]


def test_event_wire_form_is_versioned_and_json_serializable() -> None:
    class Result(BaseModel):
        value: int

    payload = event_to_dict(
        AgentFinished(
            run_id="run-1",
            parent_run_id="parent-1",
            timestamp=datetime(2026, 9, 26, 20, 30, tzinfo=UTC),
            name="events",
            status="completed",
            duration_ms=12.5,
            result=Result(value=3),
        )
    )

    assert payload == {
        "schema_version": 1,
        "kind": "agent.finished",
        "run_id": "run-1",
        "parent_run_id": "parent-1",
        "timestamp": "2026-09-26T20:30:00Z",
        "name": "events",
        "status": "completed",
        "duration_ms": 12.5,
        "result": {"value": 3},
        "error_type": None,
    }
    json.dumps(payload, allow_nan=False)


@pytest.mark.asyncio
async def test_runtime_emits_typed_agent_tool_and_usage_events() -> None:
    def increment(value: int) -> int:
        return value + 1

    provider = ScriptedFakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("call-1", "increment", {"value": 1})]),
            ModelResponse(
                content="done",
                usage=Usage(input_tokens=8, output_tokens=2, total_tokens=10),
            ),
        ]
    )
    events = []

    with event_sink(events.append):
        result = await execute_text_agent(
            provider=provider,
            spec=_spec(),
            model=_model(),
            tools=(build_tool_definition(increment),),
            generation=GenerationOptions(),
            runtime=RuntimeConfig(),
            prompt="Run it",
        )

    assert result == "done"
    assert [event.kind for event in events] == [
        "agent.started",
        "tool.started",
        "tool.finished",
        "usage",
        "agent.finished",
    ]
    assert isinstance(events[0], AgentStarted)
    assert isinstance(events[1], ToolStarted)
    assert events[1].arguments == {"value": 1}
    assert isinstance(events[2], ToolFinished)
    assert events[2].output == "2"
    assert isinstance(events[3], UsageEvent)
    assert events[3].total_tokens == 10
    assert isinstance(events[4], AgentFinished)
    assert events[4].result == "done"
    assert event_to_dict(events[1])["kind"] == "tool.started"


@pytest.mark.asyncio
async def test_history_is_snapshotted_between_system_and_new_prompt() -> None:
    history = [UserMessage("Earlier"), AssistantMessage("Previous answer")]
    provider = ScriptedFakeProvider([ModelResponse(content="current")])

    await execute_text_agent(
        provider=provider,
        spec=_spec(),
        model=_model(),
        tools=(),
        generation=GenerationOptions(),
        runtime=RuntimeConfig(),
        prompt="Now",
        history=history,
    )
    history.append(UserMessage("Too late"))

    request = provider.requests[0]
    assert [message.content for message in request.messages] == [
        "Report events.",
        "Earlier",
        "Previous answer",
        "Now",
    ]


@pytest.mark.asyncio
async def test_nested_run_records_parent_run_id() -> None:
    provider = ScriptedFakeProvider([ModelResponse(content="nested")])
    events = []

    with event_sink(events.append), run_scope("outer-run"):
        await execute_text_agent(
            provider=provider,
            spec=_spec(),
            model=_model(),
            tools=(),
            generation=GenerationOptions(),
            runtime=RuntimeConfig(),
            prompt="Nested",
        )

    assert events[0].parent_run_id == "outer-run"
    assert events[-1].parent_run_id == "outer-run"
