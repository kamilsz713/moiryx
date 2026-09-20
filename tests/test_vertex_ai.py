"""Credential-free tests for the Google Vertex AI adapter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import moiryx.providers.vertex_ai as vertex_module
from moiryx.config import VertexAIProviderConfig
from moiryx.errors import ConfigurationError, ProviderRequestError
from moiryx.messages import (
    AssistantMessage,
    RepairMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from moiryx.models import GenerationOptions, ModelRequest, ToolSchema, Usage
from moiryx.providers import (
    PROVIDER_FACTORIES,
    VertexAIProvider,
    build_vertex_request,
    normalize_vertex_response,
)


class FakeModels:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[dict[str, object]] = []

    async def generate_content(
        self,
        *,
        model: str,
        contents: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> object:
        self.requests.append({"model": model, "contents": contents, "config": config})
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.models = FakeModels(response, error)
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1


def _config() -> VertexAIProviderConfig:
    return VertexAIProviderConfig.model_validate(
        {
            "type": "vertex_ai",
            "project": "example-project",
            "location": "europe-west1",
        }
    )


def _text_response(content: str = "vertex text") -> dict[str, object]:
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": content}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 8,
            "candidatesTokenCount": 3,
            "totalTokenCount": 11,
        },
    }


def test_request_maps_messages_tools_generation_and_schema() -> None:
    schema = {
        "type": "object",
        "properties": {"accepted": {"type": "boolean"}},
        "required": ["accepted"],
    }
    request = ModelRequest(
        model="gemini-2.5-flash",
        messages=[
            SystemMessage("Follow policy"),
            UserMessage("Inspect"),
            AssistantMessage(
                content="Checking",
                tool_calls=[ToolCall("call-1", "lookup", {"id": 4})],
            ),
            ToolMessage("call-1", "lookup", '{"status":"ok"}'),
            RepairMessage("Correct the result"),
        ],
        tools=[
            ToolSchema(
                name="lookup",
                description="Look up a record",
                parameters={"type": "object"},
            )
        ],
        output_schema=schema,
        generation=GenerationOptions(
            temperature=0.2,
            max_tokens=200,
            top_p=0.8,
            seed=7,
        ),
    )

    contents, config = build_vertex_request(request)

    assert contents == [
        {"role": "user", "parts": [{"text": "Inspect"}]},
        {
            "role": "model",
            "parts": [
                {"text": "Checking"},
                {
                    "function_call": {
                        "name": "lookup",
                        "args": {"id": 4},
                        "id": "call-1",
                    }
                },
            ],
        },
        {
            "role": "tool",
            "parts": [
                {
                    "function_response": {
                        "name": "lookup",
                        "response": {"output": {"status": "ok"}},
                        "id": "call-1",
                    }
                }
            ],
        },
    ]
    assert config == {
        "system_instruction": "Follow policy\n\nCorrect the result",
        "tools": [
            {
                "function_declarations": [
                    {
                        "name": "lookup",
                        "description": "Look up a record",
                        "parameters_json_schema": {"type": "object"},
                    }
                ]
            }
        ],
        "temperature": 0.2,
        "max_output_tokens": 200,
        "top_p": 0.8,
        "seed": 7,
        "response_mime_type": "application/json",
        "response_json_schema": schema,
    }


@pytest.mark.asyncio
async def test_provider_maps_project_location_model_and_normalizes_text_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeClient(_text_response())
    constructor_arguments: list[dict[str, object]] = []

    def client_factory(**kwargs: object) -> object:
        constructor_arguments.append(kwargs)
        return SimpleNamespace(aio=fake_client)

    monkeypatch.setattr(
        vertex_module,
        "import_module",
        lambda name: SimpleNamespace(Client=client_factory),
    )
    provider = VertexAIProvider(_config())

    response = await provider.complete(
        ModelRequest(
            model="gemini-2.5-flash",
            messages=[UserMessage("Hello")],
        )
    )
    await provider.close()
    await provider.close()

    assert constructor_arguments == [
        {
            "vertexai": True,
            "project": "example-project",
            "location": "europe-west1",
            "http_options": {"api_version": "v1"},
        }
    ]
    assert fake_client.models.requests[0]["model"] == "gemini-2.5-flash"
    assert response.content == "vertex text"
    assert response.finish_reason == "STOP"
    assert response.usage == Usage(
        input_tokens=8,
        output_tokens=3,
        total_tokens=11,
        cost=None,
    )
    assert isinstance(response.raw, dict)
    assert fake_client.close_calls == 1


def test_tool_calls_and_structured_output_are_normalized() -> None:
    response = normalize_vertex_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "id": "first",
                                    "name": "lookup",
                                    "args": {"id": 1},
                                }
                            },
                            {
                                "functionCall": {
                                    "name": "lookup",
                                    "args": '{"id":',
                                }
                            },
                        ]
                    },
                    "finishReason": "MALFORMED_FUNCTION_CALL",
                }
            ],
            "parsed": {"accepted": True},
        },
        expect_structured_output=True,
    )

    assert [call.id for call in response.tool_calls] == ["first", "vertex-call-1"]
    assert response.tool_calls[0].arguments == {"id": 1}
    assert response.tool_calls[1].arguments is None
    assert response.tool_calls[1].raw_arguments == '{"id":'
    assert response.tool_calls[1].parse_error == "invalid JSON at character 6"
    assert response.structured_output == {"accepted": True}


@pytest.mark.asyncio
async def test_errors_are_normalized_without_leaking_sdk_message() -> None:
    class VertexError(Exception):
        status_code = 429

    secret = "sentinel-service-account-secret"
    provider = VertexAIProvider(
        _config(),
        client=FakeClient(error=VertexError(secret)),
    )

    with pytest.raises(ProviderRequestError) as captured:
        await provider.complete(ModelRequest(model="gemini", messages=[]))
    await provider.close()

    assert captured.value.status_code == 429
    assert captured.value.retryable is True
    assert secret not in str(captured.value)
    assert "VertexError" in str(captured.value)


def test_adc_configuration_rejects_inline_credentials() -> None:
    config = VertexAIProviderConfig.model_validate(
        {
            "type": "vertex_ai",
            "project": "project",
            "location": "global",
            "api_key": "sentinel-inline-key",
        }
    )

    with pytest.raises(ConfigurationError, match="Application Default Credentials"):
        VertexAIProvider(config, client=FakeClient())

    assert "sentinel-inline-key" not in repr(config)


def test_google_extra_and_default_factory_are_declared() -> None:
    import tomllib

    project_root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((project_root / "pyproject.toml").read_text("utf-8"))

    assert metadata["project"]["optional-dependencies"]["google"] == [
        "google-genai>=1,<2"
    ]
    assert "google-genai>=1,<2" not in metadata["project"]["dependencies"]
    assert PROVIDER_FACTORIES["vertex_ai"] is VertexAIProvider
