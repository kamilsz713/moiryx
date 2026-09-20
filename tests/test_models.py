"""Tests for provider-agnostic core models."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from pydantic import BaseModel

from moiryx.messages import (
    AssistantMessage,
    RepairMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from moiryx.models import (
    GenerationOptions,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ToolCall,
    ToolDefinition,
    ToolSchema,
    Usage,
)


def test_generation_options_are_immutable() -> None:
    options = GenerationOptions(temperature=0.2, max_tokens=512, top_p=0.9, seed=7)

    with pytest.raises(FrozenInstanceError):
        options.temperature = 0.5  # type: ignore[misc]


def test_messages_and_request_have_independent_tool_collections() -> None:
    first = ModelRequest(model="vendor/model", messages=[SystemMessage("Be concise")])
    second = ModelRequest(model="vendor/model", messages=[UserMessage("Hello")])

    first.tools.append(
        ToolSchema(
            name="read_file",
            description="Read a file",
            parameters={"type": "object"},
        )
    )

    assert second.tools == []
    assert AssistantMessage().tool_calls == []
    assert ToolMessage("call-1", "read_file", "contents").content == "contents"
    assert RepairMessage("correct the tool call").content == "correct the tool call"


def test_native_structured_contract_is_explicit_and_optional() -> None:
    schema = {"type": "object", "required": ["accepted"]}
    payload = {"accepted": True}

    request = ModelRequest(model="vendor/model", messages=[], output_schema=schema)
    response = ModelResponse(structured_output=payload)

    assert request.output_schema is schema
    assert response.structured_output is payload
    assert ModelRequest(model="vendor/model", messages=[]).output_schema is None
    assert ModelResponse().structured_output is None


def test_malformed_tool_call_preserves_raw_arguments_and_error() -> None:
    call = ToolCall(
        id="call-1",
        name="read_file",
        arguments=None,
        raw_arguments='{"path":',
        parse_error="invalid JSON",
    )

    assert call.arguments is None
    assert call.raw_arguments == '{"path":'
    assert call.parse_error == "invalid JSON"


def test_raw_response_is_optional_and_not_part_of_normal_equality_or_repr() -> None:
    usage = Usage(input_tokens=4, output_tokens=2, total_tokens=6)
    first = ModelResponse(content="done", usage=usage, raw={"secret": "payload"})
    second = ModelResponse(content="done", usage=usage)

    assert first == second
    assert "payload" not in repr(first)


def test_capabilities_default_to_no_guaranteed_features() -> None:
    assert ProviderCapabilities() == ProviderCapabilities(
        tool_calling=False,
        native_structured_output=False,
        parallel_tool_calls=False,
    )


def test_tool_definition_keeps_python_and_pydantic_types() -> None:
    class Input(BaseModel):
        path: str

    def read_file(path: str) -> str:
        return path

    definition = ToolDefinition(
        name="read_file",
        description="Read a file",
        function=read_file,
        input_model=Input,
    )

    assert definition.function("README.md") == "README.md"
    assert definition.input_model(path="README.md").path == "README.md"


def test_core_models_do_not_import_provider_sdks() -> None:
    source = Path(ModelResponse.__module__.replace(".", "/"))
    models_source = (
        Path(__file__)
        .parents[1]
        .joinpath("src", "moiryx", "models.py")
        .read_text(encoding="utf-8")
    )

    assert source.as_posix() == "moiryx/models"
    assert all(
        provider not in models_source
        for provider in (
            "import openai",
            "import azure",
            "import google",
            "import vertexai",
        )
    )
