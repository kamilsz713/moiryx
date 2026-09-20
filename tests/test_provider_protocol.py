"""Tests for the provider protocol and deterministic scripted fake."""

from __future__ import annotations

from pathlib import Path

import pytest

from moiryx.errors import ProviderRequestError
from moiryx.messages import RepairMessage, SystemMessage, ToolCall, UserMessage
from moiryx.models import (
    GenerationOptions,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ToolSchema,
    Usage,
)
from moiryx.providers import ProviderAdapter, ScriptedFakeProvider


def _request() -> ModelRequest:
    return ModelRequest(
        model="vendor/model-v1",
        messages=[
            SystemMessage("Follow instructions"),
            UserMessage("Run the check"),
            RepairMessage("Correct malformed arguments"),
        ],
        tools=[
            ToolSchema(
                name="lookup",
                description="Look up a record",
                parameters={"type": "object"},
            )
        ],
        generation=GenerationOptions(temperature=0.2),
    )


def test_scripted_fake_satisfies_provider_protocol() -> None:
    provider = ScriptedFakeProvider([])

    assert isinstance(provider, ProviderAdapter)
    assert provider.capabilities == ProviderCapabilities(
        tool_calling=True,
        native_structured_output=True,
        parallel_tool_calls=True,
    )


@pytest.mark.asyncio
async def test_fake_scripts_text_tool_and_error_responses_in_order() -> None:
    text_response = ModelResponse(
        content="ready",
        finish_reason="stop",
        usage=Usage(input_tokens=3, output_tokens=1, total_tokens=4),
    )
    tool_response = ModelResponse(
        tool_calls=[
            ToolCall(
                id="call-1",
                name="lookup",
                arguments={"record_id": 7},
                raw_arguments='{"record_id":7}',
            )
        ],
        finish_reason="tool_calls",
    )
    scripted_error = ProviderRequestError("temporary provider failure")
    provider = ScriptedFakeProvider(
        [text_response, tool_response, scripted_error],
    )
    request = _request()

    first = await provider.complete(request)
    second = await provider.complete(request)

    assert first == text_response
    assert second == tool_response
    assert second.tool_calls[0].raw_arguments == '{"record_id":7}'
    with pytest.raises(ProviderRequestError) as captured:
        await provider.complete(request)
    assert captured.value is scripted_error
    assert provider.remaining == 0
    assert len(provider.requests) == 3


@pytest.mark.asyncio
async def test_recorded_requests_are_snapshots_not_live_history_references() -> None:
    provider = ScriptedFakeProvider([ModelResponse(content="done")])
    request = _request()

    await provider.complete(request)
    request.messages.append(UserMessage("later mutation"))
    request.tools[0].parameters["mutated"] = True

    recorded = provider.requests[0]
    assert len(recorded.messages) == 3
    assert recorded.tools[0].parameters == {"type": "object"}


@pytest.mark.asyncio
async def test_returned_responses_are_detached_from_script_input() -> None:
    scripted = ModelResponse(content="original", tool_calls=[])
    provider = ScriptedFakeProvider([scripted])

    returned = await provider.complete(_request())
    returned.content = "changed"
    returned.tool_calls.append(ToolCall("new", "lookup", {}))

    assert scripted.content == "original"
    assert scripted.tool_calls == []


@pytest.mark.asyncio
async def test_exhaustion_and_closed_state_are_explicit() -> None:
    provider = ScriptedFakeProvider([])

    with pytest.raises(AssertionError, match="queue is exhausted"):
        await provider.complete(_request())

    await provider.close()
    await provider.close()

    assert provider.closed is True
    assert provider.close_calls == 1
    with pytest.raises(RuntimeError, match="closed"):
        await provider.complete(_request())


def test_capabilities_can_be_overridden_per_fake() -> None:
    capabilities = ProviderCapabilities(native_structured_output=True)

    provider = ScriptedFakeProvider([], capabilities=capabilities)

    assert provider.capabilities is capabilities


@pytest.mark.parametrize("invalid", (None, "response", 42))
def test_script_rejects_invalid_items(invalid: object) -> None:
    with pytest.raises(TypeError, match="ModelResponse"):
        ScriptedFakeProvider([invalid])  # type: ignore[list-item]


def test_provider_protocol_does_not_import_vendor_sdks() -> None:
    source = (
        Path(__file__)
        .parents[1]
        .joinpath("src", "moiryx", "providers", "registry.py")
        .read_text(encoding="utf-8")
    )

    assert all(
        vendor not in source
        for vendor in ("import openai", "import azure", "import google")
    )


def test_repair_instruction_is_not_a_user_message() -> None:
    instruction = _request().messages[2]

    assert isinstance(instruction, RepairMessage)
    assert not isinstance(instruction, UserMessage)
