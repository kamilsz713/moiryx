"""Tests for the provider-neutral text-agent runtime loop."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest

from moiryx.agent_spec import AgentSpec
from moiryx.config import RuntimeConfig
from moiryx.errors import AgentProtocolError, MaxStepsExceeded, ProviderRequestError
from moiryx.messages import (
    AssistantMessage,
    RepairMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from moiryx.model_registry import ResolvedModel
from moiryx.models import GenerationOptions, ModelResponse, ToolDefinition
from moiryx.providers import ScriptedFakeProvider
from moiryx.retry import ProviderRetry
from moiryx.runtime import execute_text_agent
from moiryx.tools.definition import build_tool_definition


def _spec(*, max_steps: int = 5) -> AgentSpec:
    return AgentSpec(
        name="reviewer",
        model_alias="strong",
        instructions="Review carefully.",
        tool_names=(),
        output_model=None,
        max_steps=max_steps,
        generation=GenerationOptions(),
        source_path=Path("reviewer.md"),
    )


def _model() -> ResolvedModel:
    return ResolvedModel(
        alias="strong",
        provider="local",
        model="vendor/model-v1",
        generation=GenerationOptions(),
        provider_options=MappingProxyType({}),
    )


async def _execute(
    provider: ScriptedFakeProvider,
    *,
    tools: tuple[ToolDefinition, ...] = (),
    max_steps: int = 5,
    repair_attempts: int = 2,
    provider_retry: ProviderRetry | None = None,
) -> str:
    return await execute_text_agent(
        provider=provider,
        spec=_spec(max_steps=max_steps),
        model=_model(),
        tools=tools,
        generation=GenerationOptions(temperature=0.2),
        runtime=RuntimeConfig(tool_call_repair_attempts=repair_attempts),
        prompt="Check this change",
        provider_retry=provider_retry,
    )


@pytest.mark.asyncio
async def test_first_response_content_is_returned_as_text() -> None:
    provider = ScriptedFakeProvider([ModelResponse(content="accepted")])

    result = await _execute(provider)

    assert result == "accepted"
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.model == "vendor/model-v1"
    assert request.generation.temperature == 0.2
    assert request.tools == []
    assert request.messages == [
        SystemMessage("Review carefully."),
        UserMessage("Check this change"),
    ]


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_tool_result_is_sent_in_order_before_later_final_content() -> None:
    def increment(value: int) -> int:
        """Increment a number."""
        return value + 1

    definition = build_tool_definition(increment)
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                content="Calling a tool",
                tool_calls=[
                    ToolCall("call-1", "increment", {"value": 2}),
                ],
            ),
            ModelResponse(content="The answer is 3"),
        ]
    )

    result = await _execute(provider, tools=(definition,))

    assert result == "The answer is 3"
    assert len(provider.requests) == 2
    second = provider.requests[1]
    assert [type(message) for message in second.messages] == [
        SystemMessage,
        UserMessage,
        AssistantMessage,
        ToolMessage,
    ]
    assistant = second.messages[2]
    tool_message = second.messages[3]
    assert isinstance(assistant, AssistantMessage)
    assert assistant.content == "Calling a tool"
    assert assistant.tool_calls[0].id == "call-1"
    assert isinstance(tool_message, ToolMessage)
    assert (tool_message.tool_call_id, tool_message.name, tool_message.content) == (
        "call-1",
        "increment",
        "3",
    )
    assert [schema.name for schema in second.tools] == ["increment"]


@pytest.mark.asyncio
async def test_multiple_tool_calls_execute_sequentially_and_keep_ids() -> None:
    execution_order: list[int] = []

    def record(value: int) -> str:
        execution_order.append(value)
        return f"recorded:{value}"

    definition = build_tool_definition(record)
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall("first", "record", {"value": 1}),
                    ToolCall("second", "record", {"value": 2}),
                    ToolCall("third", "record", {"value": 3}),
                ]
            ),
            ModelResponse(content="done"),
        ]
    )

    assert await _execute(provider, tools=(definition,)) == "done"

    assert execution_order == [1, 2, 3]
    messages = provider.requests[1].messages[-3:]
    assert all(isinstance(message, ToolMessage) for message in messages)
    assert [
        (message.tool_call_id, message.name)
        for message in messages
        if isinstance(message, ToolMessage)
    ] == [("first", "record"), ("second", "record"), ("third", "record")]


@pytest.mark.asyncio
async def test_entire_batch_preflight_finishes_before_first_execution() -> None:
    mutations: list[int] = []

    def mutate(value: int) -> str:
        mutations.append(value)
        return "mutated"

    def inspect_count(count: int) -> int:
        return count

    definitions = (
        build_tool_definition(mutate),
        build_tool_definition(inspect_count),
    )
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall("valid", "mutate", {"value": 1}),
                    ToolCall("invalid", "inspect_count", {"count": "bad"}),
                ]
            ),
            ModelResponse(content="recovered"),
        ]
    )

    result = await _execute(provider, tools=definitions)

    assert result == "recovered"
    assert mutations == []
    second_messages = provider.requests[1].messages
    assert isinstance(second_messages[-2], AssistantMessage)
    assert isinstance(second_messages[-1], ToolMessage)
    assert second_messages[-1].tool_call_id == "invalid"


@pytest.mark.asyncio
async def test_missing_call_id_uses_internal_repair_instruction() -> None:
    def lookup(value: int) -> int:
        return value

    provider = ScriptedFakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("", "lookup", {})]),
            ModelResponse(content="recovered"),
        ]
    )

    result = await _execute(provider, tools=(build_tool_definition(lookup),))

    assert result == "recovered"
    assert isinstance(provider.requests[1].messages[-1], RepairMessage)


@pytest.mark.asyncio
async def test_tool_execution_error_is_returned_without_secret_or_stack() -> None:
    def explode() -> str:
        raise RuntimeError("sentinel-secret")

    provider = ScriptedFakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("call-1", "explode", {})]),
            ModelResponse(content="continued"),
        ]
    )

    result = await _execute(provider, tools=(build_tool_definition(explode),))

    assert result == "continued"
    message = provider.requests[1].messages[-1]
    assert isinstance(message, ToolMessage)
    assert (
        message.content == "ToolExecutionError: Tool execution failed with RuntimeError"
    )
    assert "sentinel-secret" not in message.content
    assert "Traceback" not in message.content


@pytest.mark.asyncio
async def test_empty_provider_response_has_protocol_error_with_run_context() -> None:
    provider = ScriptedFakeProvider([ModelResponse()])

    with pytest.raises(AgentProtocolError) as captured:
        await _execute(provider)

    context = captured.value.context
    assert context["agent"] == "reviewer"
    assert context["model"] == "strong"
    assert context["provider"] == "local"
    assert context["model_id"] == "vendor/model-v1"
    assert isinstance(context["run"], str)


@pytest.mark.asyncio
async def test_max_steps_error_contains_limit_and_run_context() -> None:
    calls = 0

    def keep_going() -> str:
        nonlocal calls
        calls += 1
        return "again"

    definition = build_tool_definition(keep_going)
    provider = ScriptedFakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("one", "keep_going", {})]),
            ModelResponse(tool_calls=[ToolCall("two", "keep_going", {})]),
        ]
    )

    with pytest.raises(MaxStepsExceeded) as captured:
        await _execute(provider, tools=(definition,), max_steps=2)

    assert calls == 2
    assert captured.value.context["limit"] == 2
    assert captured.value.context["agent"] == "reviewer"
    assert isinstance(captured.value.context["run"], str)


@pytest.mark.asyncio
async def test_empty_string_is_valid_final_content() -> None:
    provider = ScriptedFakeProvider([ModelResponse(content="")])

    assert await _execute(provider) == ""


@pytest.mark.asyncio
async def test_provider_retry_is_not_a_model_step_or_tool_repair_attempt() -> None:
    async def no_sleep(delay: float) -> None:
        assert delay >= 0

    def lookup(value: int) -> int:
        return value

    definition = build_tool_definition(lookup)
    provider = ScriptedFakeProvider(
        [
            ProviderRequestError("busy", status_code=503),
            ModelResponse(tool_calls=[ToolCall("bad", "lookup", {})]),
            ModelResponse(content="recovered"),
        ]
    )
    retry = ProviderRetry(1, sleep=no_sleep, random_source=lambda: 0.5)

    result = await _execute(
        provider,
        tools=(definition,),
        max_steps=2,
        repair_attempts=1,
        provider_retry=retry,
    )

    assert result == "recovered"
    assert len(provider.requests) == 3
    assert provider.requests[0].messages == provider.requests[1].messages
    assert isinstance(provider.requests[2].messages[-1], ToolMessage)
