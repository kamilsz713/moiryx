"""Mock-transport coverage for the Azure OpenAI adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from moiryx.config import AzureOpenAIProviderConfig
from moiryx.messages import UserMessage
from moiryx.models import ModelRequest, ToolSchema, Usage
from moiryx.providers import AzureOpenAIProvider, OpenAICompatibleProvider


def _config(
    *,
    api_key: str | None = None,
    headers: dict[str, str] | None = None,
) -> AzureOpenAIProviderConfig:
    payload: dict[str, object] = {
        "type": "azure_openai",
        "endpoint": "https://azure-openai.example/",
        "api_version": "2025-04-01-preview",
    }
    if api_key is not None:
        payload["api_key"] = api_key
    if headers is not None:
        payload["headers"] = headers
    return AzureOpenAIProviderConfig.model_validate(payload)


def _success(content: str | None = "done") -> dict[str, object]:
    return {
        "id": "azure-completion-1",
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 7,
            "completion_tokens": 2,
            "total_tokens": 9,
        },
    }


@pytest.mark.asyncio
async def test_deployment_endpoint_version_key_and_text_are_mapped() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_success("azure text"))

    secret = "sentinel-azure-key"
    provider = AzureOpenAIProvider(
        _config(api_key=secret, headers={"X-Tenant": "alpha"}),
        transport=httpx.MockTransport(handler),
    )

    response = await provider.complete(
        ModelRequest(
            model="review/deployment",
            messages=[UserMessage("Review")],
        )
    )
    await provider.close()

    assert isinstance(provider, OpenAICompatibleProvider)
    assert str(captured[0].url) == (
        "https://azure-openai.example/openai/deployments/"
        "review%2Fdeployment/chat/completions?api-version=2025-04-01-preview"
    )
    assert captured[0].headers["api-key"] == secret
    assert captured[0].headers["X-Tenant"] == "alpha"
    assert json.loads(captured[0].content) == {
        "messages": [{"role": "user", "content": "Review"}]
    }
    assert response.content == "azure text"
    assert response.usage == Usage(
        input_tokens=7,
        output_tokens=2,
        total_tokens=9,
        cost=None,
    )
    assert isinstance(response.raw, dict)
    assert secret not in repr(provider)


@pytest.mark.asyncio
async def test_explicit_bearer_auth_takes_precedence_over_configured_key() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_success())

    provider = AzureOpenAIProvider(
        _config(
            api_key="unused-key",
            headers={"Authorization": "Bearer explicit-token"},
        ),
        transport=httpx.MockTransport(handler),
    )

    await provider.complete(ModelRequest(model="deployment", messages=[]))
    await provider.close()

    assert captured[0].headers["Authorization"] == "Bearer explicit-token"
    assert "api-key" not in captured[0].headers
    assert "unused-key" not in repr(provider)
    assert "explicit-token" not in repr(provider)


@pytest.mark.asyncio
async def test_tool_calls_and_malformed_arguments_use_normalized_core_types() -> None:
    response_payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "valid",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": '{"id":4}',
                            },
                        },
                        {
                            "id": "broken",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": '{"id":',
                            },
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    provider = AzureOpenAIProvider(
        _config(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=response_payload)
        ),
    )

    response = await provider.complete(ModelRequest(model="deployment", messages=[]))
    await provider.close()

    assert [call.id for call in response.tool_calls] == ["valid", "broken"]
    assert response.tool_calls[0].arguments == {"id": 4}
    assert response.tool_calls[1].arguments is None
    assert response.tool_calls[1].raw_arguments == '{"id":'
    assert response.tool_calls[1].parse_error == "invalid JSON at character 6"


@pytest.mark.asyncio
async def test_structured_schema_and_response_are_mapped() -> None:
    captured: list[dict[str, object]] = []
    schema = {
        "type": "object",
        "properties": {"accepted": {"type": "boolean"}},
        "required": ["accepted"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=_success('{"accepted":true}'))

    provider = AzureOpenAIProvider(
        _config(),
        transport=httpx.MockTransport(handler),
    )

    response = await provider.complete(
        ModelRequest(
            model="deployment",
            messages=[],
            tools=[
                ToolSchema(
                    name="lookup",
                    description="Look up a record",
                    parameters={"type": "object"},
                )
            ],
            output_schema=schema,
        )
    )
    await provider.close()

    assert captured[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "moiryx_result",
            "strict": True,
            "schema": schema,
        },
    }
    assert captured[0]["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Look up a record",
                "parameters": {"type": "object"},
            },
        }
    ]
    assert response.structured_output == {"accepted": True}
