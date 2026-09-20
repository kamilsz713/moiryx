"""Tests for synthetic-tool and native-schema structured output."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from moiryx.agent_spec import AgentSpec
from moiryx.config import RuntimeConfig
from moiryx.errors import (
    AgentProtocolError,
    ProviderCapabilityError,
    ProviderRequestError,
    StructuredOutputError,
)
from moiryx.messages import RepairMessage, ToolCall, ToolMessage
from moiryx.model_registry import ResolvedModel
from moiryx.models import (
    GenerationOptions,
    ModelResponse,
    ProviderCapabilities,
    ToolDefinition,
)
from moiryx.output import build_final_tool
from moiryx.providers import ScriptedFakeProvider
from moiryx.retry import ProviderRetry
from moiryx.runtime import execute_structured_agent
from moiryx.tools import FINAL_TOOL_NAME
from moiryx.tools.definition import build_tool_definition


class Severity(StrEnum):
    LOW = "low"
    HIGH = "high"


class Finding(BaseModel):
    severity: Severity
    message: str = Field(min_length=3)


class ReviewResult(BaseModel):
    decision: Literal["accept", "revise"]
    score: float = Field(ge=0, le=1)
    findings: list[Finding]


def _valid_result() -> dict[str, object]:
    return {
        "decision": "revise",
        "score": 0.75,
        "findings": [{"severity": "high", "message": "Fix validation"}],
    }


def _spec(
    *,
    max_steps: int = 6,
    tool_names: tuple[str, ...] = (),
) -> AgentSpec:
    return AgentSpec(
        name="reviewer",
        model_alias="strong",
        instructions="Review carefully.",
        tool_names=tool_names,
        output_model=ReviewResult,
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


def _final(arguments: dict[str, object], call_id: str = "final") -> ModelResponse:
    return ModelResponse(tool_calls=[ToolCall(call_id, FINAL_TOOL_NAME, arguments)])


async def _execute(
    provider: ScriptedFakeProvider,
    *,
    tools: tuple[ToolDefinition, ...] = (),
    capabilities: ProviderCapabilities | None = None,
    max_steps: int = 6,
    structured_retries: int = 2,
    tool_retries: int = 2,
    provider_retry: ProviderRetry | None = None,
) -> BaseModel:
    tool_names = tuple(definition.name for definition in tools)
    return await execute_structured_agent(
        provider=provider,
        spec=_spec(max_steps=max_steps, tool_names=tool_names),
        model=_model(),
        tools=tools,
        capabilities=capabilities
        or ProviderCapabilities(
            tool_calling=True,
            native_structured_output=True,
        ),
        generation=GenerationOptions(temperature=0.2),
        runtime=RuntimeConfig(
            structured_output_retries=structured_retries,
            tool_call_repair_attempts=tool_retries,
        ),
        prompt="Check this change",
        provider_retry=provider_retry,
    )


def test_final_tool_uses_output_model_schema_and_cannot_execute() -> None:
    definition = build_final_tool(ReviewResult)

    assert definition.name == FINAL_TOOL_NAME
    assert definition.input_model is ReviewResult
    assert definition.schema.parameters == ReviewResult.model_json_schema()
    with pytest.raises(AgentProtocolError, match="cannot be executed"):
        definition.function(**_valid_result())


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_valid_final_call_returns_exact_nested_pydantic_model() -> None:
    provider = ScriptedFakeProvider([_final(_valid_result())])

    result = await _execute(provider)

    assert type(result) is ReviewResult
    assert isinstance(result.findings[0], Finding)
    assert result.findings[0].severity is Severity.HIGH
    request = provider.requests[0]
    assert [schema.name for schema in request.tools] == [FINAL_TOOL_NAME]
    assert request.tools[0].parameters == ReviewResult.model_json_schema()
    assert request.output_schema is None
    assert FINAL_TOOL_NAME in request.messages[0].content


@pytest.mark.asyncio
async def test_normal_tool_can_run_before_the_final_call() -> None:
    calls: list[int] = []

    def inspect_score(value: int) -> int:
        calls.append(value)
        return value

    tool = build_tool_definition(inspect_score)
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[ToolCall("inspect", "inspect_score", {"value": 7})]
            ),
            _final(_valid_result()),
        ]
    )

    result = await _execute(provider, tools=(tool,))

    assert type(result) is ReviewResult
    assert calls == [7]
    assert [schema.name for schema in provider.requests[0].tools] == [
        "inspect_score",
        FINAL_TOOL_NAME,
    ]
    message = provider.requests[1].messages[-1]
    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "inspect"


@pytest.mark.asyncio
async def test_invalid_final_arguments_use_structured_correction() -> None:
    invalid = _valid_result()
    invalid["decision"] = "maybe"
    invalid["score"] = 4.0
    provider = ScriptedFakeProvider(
        [_final(invalid, "bad-final"), _final(_valid_result())]
    )

    result = await _execute(provider, structured_retries=1, tool_retries=0)

    assert type(result) is ReviewResult
    feedback = provider.requests[1].messages[-1]
    assert isinstance(feedback, ToolMessage)
    assert feedback.tool_call_id == "bad-final"
    assert feedback.name == FINAL_TOOL_NAME
    assert "Final structured output is invalid" in feedback.content
    assert "decision" in feedback.content
    assert "score" in feedback.content


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_plain_markdown_json_is_never_parsed_as_the_result() -> None:
    markdown = '```json\n{"decision": "accept"}\n```'
    provider = ScriptedFakeProvider(
        [ModelResponse(content=markdown), _final(_valid_result())]
    )

    result = await _execute(provider, structured_retries=1)

    assert type(result) is ReviewResult
    feedback = provider.requests[1].messages[-1]
    assert isinstance(feedback, RepairMessage)
    assert "Markdown" in feedback.content
    assert markdown not in feedback.content


@pytest.mark.asyncio
async def test_final_and_normal_tool_are_rejected_without_execution() -> None:
    mutations: list[int] = []

    def mutate(value: int) -> None:
        mutations.append(value)

    tool = build_tool_definition(mutate)
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall("normal", "mutate", {"value": 1}),
                    ToolCall("final", FINAL_TOOL_NAME, _valid_result()),
                ]
            ),
            _final(_valid_result()),
        ]
    )

    result = await _execute(provider, tools=(tool,), structured_retries=1)

    assert type(result) is ReviewResult
    assert mutations == []
    feedback = provider.requests[1].messages[-1]
    assert isinstance(feedback, RepairMessage)
    assert "alone" in feedback.content


@pytest.mark.asyncio
async def test_multiple_final_calls_require_a_corrective_round() -> None:
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall("first", FINAL_TOOL_NAME, _valid_result()),
                    ToolCall("second", FINAL_TOOL_NAME, _valid_result()),
                ]
            ),
            _final(_valid_result()),
        ]
    )

    result = await _execute(provider, structured_retries=1)

    assert type(result) is ReviewResult
    feedback = provider.requests[1].messages[-1]
    assert isinstance(feedback, RepairMessage)
    assert "exactly once" in feedback.content


@pytest.mark.asyncio
async def test_structured_budget_exhaustion_has_run_context() -> None:
    provider = ScriptedFakeProvider(
        [ModelResponse(content="plain"), ModelResponse(content="still plain")]
    )

    with pytest.raises(StructuredOutputError) as captured:
        await _execute(provider, structured_retries=1)

    assert captured.value.context["attempts"] == 1
    assert captured.value.context["limit"] == 1
    assert captured.value.context["agent"] == "reviewer"
    assert captured.value.context["provider"] == "local"
    assert isinstance(captured.value.context["run"], str)


@pytest.mark.asyncio
async def test_provider_tool_and_structured_retry_budgets_are_independent() -> None:
    async def no_sleep(delay: float) -> None:
        assert delay >= 0

    def lookup(value: int) -> int:
        return value

    tool = build_tool_definition(lookup)
    provider = ScriptedFakeProvider(
        [
            ProviderRequestError("busy", status_code=503),
            ModelResponse(tool_calls=[ToolCall("bad-tool", "lookup", {})]),
            ModelResponse(content="plain result"),
            _final(_valid_result()),
        ]
    )
    retry = ProviderRetry(1, sleep=no_sleep, random_source=lambda: 0.5)

    result = await _execute(
        provider,
        tools=(tool,),
        max_steps=3,
        structured_retries=1,
        tool_retries=1,
        provider_retry=retry,
    )

    assert type(result) is ReviewResult
    assert len(provider.requests) == 4
    assert provider.requests[0].messages == provider.requests[1].messages
    assert isinstance(provider.requests[2].messages[-1], ToolMessage)
    assert isinstance(provider.requests[3].messages[-1], RepairMessage)


@pytest.mark.asyncio
async def test_native_schema_path_returns_the_declared_model() -> None:
    capabilities = ProviderCapabilities(native_structured_output=True)
    provider = ScriptedFakeProvider(
        [ModelResponse(structured_output=_valid_result())],
        capabilities=capabilities,
    )

    result = await _execute(provider, capabilities=capabilities)

    assert type(result) is ReviewResult
    request = provider.requests[0]
    assert request.tools == []
    assert request.output_schema == ReviewResult.model_json_schema()
    assert "native structured output" in request.messages[0].content


@pytest.mark.asyncio
async def test_native_schema_rejects_plain_json_and_invalid_constraints() -> None:
    capabilities = ProviderCapabilities(native_structured_output=True)
    invalid = _valid_result()
    invalid["score"] = -1.0
    provider = ScriptedFakeProvider(
        [
            ModelResponse(content='{"decision":"accept"}'),
            ModelResponse(structured_output=invalid),
            ModelResponse(structured_output=_valid_result()),
        ],
        capabilities=capabilities,
    )

    result = await _execute(
        provider,
        capabilities=capabilities,
        structured_retries=2,
    )

    assert type(result) is ReviewResult
    first_feedback = provider.requests[1].messages[-1]
    second_feedback = provider.requests[2].messages[-1]
    assert isinstance(first_feedback, RepairMessage)
    assert "Plain text" in first_feedback.content
    assert isinstance(second_feedback, RepairMessage)
    assert "score" in second_feedback.content


@pytest.mark.asyncio
async def test_tool_calling_is_preferred_when_both_modes_are_available() -> None:
    capabilities = ProviderCapabilities(
        tool_calling=True,
        native_structured_output=True,
    )
    provider = ScriptedFakeProvider(
        [_final(_valid_result())], capabilities=capabilities
    )

    result = await _execute(provider, capabilities=capabilities)

    assert type(result) is ReviewResult
    assert [schema.name for schema in provider.requests[0].tools] == [FINAL_TOOL_NAME]
    assert provider.requests[0].output_schema is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("capabilities", "with_tool"),
    [
        (ProviderCapabilities(), False),
        (ProviderCapabilities(native_structured_output=True), True),
    ],
)
async def test_insufficient_capabilities_fail_before_provider_request(
    capabilities: ProviderCapabilities,
    with_tool: bool,
) -> None:
    def lookup(value: int) -> int:
        return value

    tools = (build_tool_definition(lookup),) if with_tool else ()
    provider = ScriptedFakeProvider([], capabilities=capabilities)

    with pytest.raises(ProviderCapabilityError):
        await _execute(provider, tools=tools, capabilities=capabilities)

    assert provider.requests == []
