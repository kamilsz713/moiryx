"""Mock-transport tests for the OpenAI-compatible provider adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from moiryx.config import MoiryxConfig, OpenAICompatibleProviderConfig
from moiryx.errors import ProviderRequestError
from moiryx.messages import (
    AssistantMessage,
    RepairMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from moiryx.models import (
    GenerationOptions,
    ModelRequest,
    ProviderCapabilities,
    ToolSchema,
    Usage,
)
from moiryx.providers import (
    OpenAICompatibleProvider,
    ProviderRegistry,
    build_openai_request,
    normalize_openai_response,
)


def _config(
    *,
    api_key: str | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 12,
) -> OpenAICompatibleProviderConfig:
    payload: dict[str, object] = {
        "type": "openai_compatible",
        "base_url": "https://local.example/v1",
        "timeout_seconds": timeout_seconds,
    }
    if api_key is not None:
        payload["api_key"] = api_key
    if headers is not None:
        payload["headers"] = headers
    return OpenAICompatibleProviderConfig.model_validate(payload)


def _success(content: str = "done") -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ]
    }


def test_request_mapping_is_minimal_and_preserves_message_protocol() -> None:
    request = ModelRequest(
        model="org/model-v1",
        messages=[
            SystemMessage("Follow policy"),
            UserMessage("Inspect 7"),
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        "call-7",
                        "lookup",
                        {"record_id": 7},
                        raw_arguments='{"record_id":7}',
                    )
                ]
            ),
            ToolMessage("call-7", "lookup", '{"status":"ok"}'),
            RepairMessage("Return a corrected call"),
        ],
        tools=[
            ToolSchema(
                name="lookup",
                description="Look up a record",
                parameters={
                    "type": "object",
                    "properties": {"record_id": {"type": "integer"}},
                    "required": ["record_id"],
                },
            )
        ],
        generation=GenerationOptions(
            temperature=0.2,
            max_tokens=200,
            top_p=0.9,
            seed=4,
        ),
    )

    payload = build_openai_request(request)

    assert set(payload) == {
        "model",
        "messages",
        "tools",
        "temperature",
        "max_tokens",
        "top_p",
        "seed",
    }
    assert payload["model"] == "org/model-v1"
    assert payload["messages"] == [
        {"role": "system", "content": "Follow policy"},
        {"role": "user", "content": "Inspect 7"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-7",
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "arguments": '{"record_id":7}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-7",
            "content": '{"status":"ok"}',
        },
        {"role": "system", "content": "Return a corrected call"},
    ]
    assert payload["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Look up a record",
                "parameters": {
                    "type": "object",
                    "properties": {"record_id": {"type": "integer"}},
                    "required": ["record_id"],
                },
            },
        }
    ]


def test_empty_optional_request_fields_are_omitted() -> None:
    payload = build_openai_request(
        ModelRequest(
            model="model",
            messages=[UserMessage("Hello")],
        )
    )

    assert payload == {
        "model": "model",
        "messages": [{"role": "user", "content": "Hello"}],
    }


@pytest.mark.asyncio
async def test_transport_maps_url_headers_timeout_and_reuses_client() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_success())

    secret = "sentinel-api-key"
    provider = OpenAICompatibleProvider(
        _config(
            api_key=secret,
            headers={"X-Tenant": "alpha", "X-Private-Token": "header-secret"},
        ),
        transport=httpx.MockTransport(handler),
    )
    request = ModelRequest(model="model", messages=[UserMessage("Hello")])

    first = await provider.complete(request)
    second = await provider.complete(request)

    assert first.content == second.content == "done"
    assert len(requests) == 2
    for recorded in requests:
        assert str(recorded.url) == "https://local.example/v1/chat/completions"
        assert recorded.headers["Authorization"] == f"Bearer {secret}"
        assert recorded.headers["X-Tenant"] == "alpha"
        assert recorded.headers["X-Private-Token"] == "header-secret"
        timeout = recorded.extensions["timeout"]
        assert isinstance(timeout, dict)
        assert set(timeout.values()) == {12.0}
        assert json.loads(recorded.content) == {
            "model": "model",
            "messages": [{"role": "user", "content": "Hello"}],
        }
    rendered = repr(provider)
    assert secret not in rendered
    assert "header-secret" not in rendered

    await provider.close()
    await provider.close()

    assert provider.closed is True
    with pytest.raises(ProviderRequestError, match="closed"):
        await provider.complete(request)


def test_explicit_authorization_header_takes_precedence_over_api_key() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_success())

    provider = OpenAICompatibleProvider(
        _config(
            api_key="unused-key",
            headers={"authorization": "Custom sentinel-authorization"},
        ),
        transport=httpx.MockTransport(handler),
    )

    async def run() -> None:
        await provider.complete(ModelRequest(model="model", messages=[]))
        await provider.close()

    import asyncio

    asyncio.run(run())

    assert captured[0].headers["Authorization"] == "Custom sentinel-authorization"
    assert "unused-key" not in repr(provider)
    assert "sentinel-authorization" not in repr(provider)


def test_text_finish_reason_usage_and_raw_payload_are_normalized() -> None:
    payload = {
        "id": "completion-1",
        "choices": [
            {
                "message": {"role": "assistant", "content": "accepted"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 8,
            "completion_tokens": 3,
            "total_tokens": 11,
            "cost": 0.004,
        },
    }

    response = normalize_openai_response(payload)

    assert response.content == "accepted"
    assert response.finish_reason == "stop"
    assert response.tool_calls == []
    assert response.usage == Usage(
        input_tokens=8,
        output_tokens=3,
        total_tokens=11,
        cost=0.004,
    )
    assert response.raw is payload


def test_tool_calls_keep_order_ids_names_and_malformed_raw_arguments() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "first",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": '{"record_id":1}',
                            },
                        },
                        {
                            "id": "broken",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": '{"record_id":',
                            },
                        },
                        {
                            "id": "third",
                            "type": "function",
                            "function": {
                                "name": "submit",
                                "arguments": {"accepted": True},
                            },
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }

    response = normalize_openai_response(payload)

    assert [call.id for call in response.tool_calls] == ["first", "broken", "third"]
    assert [call.name for call in response.tool_calls] == [
        "lookup",
        "lookup",
        "submit",
    ]
    assert response.tool_calls[0].arguments == {"record_id": 1}
    assert response.tool_calls[0].raw_arguments == '{"record_id":1}'
    assert response.tool_calls[0].parse_error is None
    assert response.tool_calls[1].arguments is None
    assert response.tool_calls[1].raw_arguments == '{"record_id":'
    assert response.tool_calls[1].parse_error == "invalid JSON at character 13"
    assert response.tool_calls[2].arguments == {"accepted": True}
    assert response.finish_reason == "tool_calls"


def test_identifiable_call_with_missing_function_is_preserved_for_repair() -> None:
    response = normalize_openai_response(
        {
            "choices": [
                {
                    "message": {"tool_calls": [{"id": "damaged"}]},
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )

    assert response.tool_calls == [
        ToolCall(
            id="damaged",
            name="",
            arguments=None,
            parse_error="tool function payload is missing",
        )
    ]


@pytest.mark.asyncio
async def test_explicit_native_schema_maps_request_and_normalizes_json_content() -> (
    None
):
    captured: list[dict[str, object]] = []
    schema = {
        "type": "object",
        "properties": {"accepted": {"type": "boolean"}},
        "required": ["accepted"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=_success('{"accepted":true}'))

    provider = OpenAICompatibleProvider(
        _config(),
        transport=httpx.MockTransport(handler),
    )
    request = ModelRequest(model="model", messages=[], output_schema=schema)

    response = await provider.complete(request)
    await provider.close()

    assert captured[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "moiryx_result",
            "strict": True,
            "schema": schema,
        },
    }
    assert response.structured_output == {"accepted": True}
    assert response.content == '{"accepted":true}'
    without_schema = normalize_openai_response(_success('{"accepted":true}'))
    assert without_schema.structured_output is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "retryable"),
    [(400, False), (401, False), (429, True), (503, True)],
)
async def test_http_errors_are_classified_without_leaking_response_body(
    status: int,
    retryable: bool,
) -> None:
    secret = "sentinel-response-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": secret}})

    provider = OpenAICompatibleProvider(
        _config(api_key="sentinel-auth-secret"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderRequestError) as captured:
        await provider.complete(ModelRequest(model="model", messages=[]))
    await provider.close()

    error = captured.value
    assert error.status_code == status
    assert error.retryable is retryable
    assert secret not in str(error)
    assert "sentinel-auth-secret" not in str(error)


@pytest.mark.asyncio
async def test_timeout_and_network_errors_have_retryable_classification() -> None:
    request = ModelRequest(model="model", messages=[])

    def timeout_handler(http_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("sentinel-timeout-secret", request=http_request)

    timeout_provider = OpenAICompatibleProvider(
        _config(),
        transport=httpx.MockTransport(timeout_handler),
    )
    with pytest.raises(TimeoutError) as timeout_error:
        await timeout_provider.complete(request)
    await timeout_provider.close()

    def network_handler(http_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sentinel-network-secret", request=http_request)

    network_provider = OpenAICompatibleProvider(
        _config(),
        transport=httpx.MockTransport(network_handler),
    )
    with pytest.raises(ProviderRequestError) as network_error:
        await network_provider.complete(request)
    await network_provider.close()

    assert "sentinel-timeout-secret" not in str(timeout_error.value)
    assert network_error.value.retryable is True
    assert "sentinel-network-secret" not in str(network_error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": []}]}),
    ],
)
async def test_invalid_success_responses_are_explicit_non_retryable_errors(
    response: httpx.Response,
) -> None:
    provider = OpenAICompatibleProvider(
        _config(),
        transport=httpx.MockTransport(lambda request: response),
    )

    with pytest.raises(ProviderRequestError) as captured:
        await provider.complete(ModelRequest(model="model", messages=[]))
    await provider.close()

    assert captured.value.retryable is False
    assert "invalid chat-completions response" in str(captured.value)


@pytest.mark.asyncio
async def test_default_factory_is_registered_cached_and_cleaned_up() -> None:
    config = MoiryxConfig.model_validate(
        {
            "providers": {
                "local": {
                    "type": "openai_compatible",
                    "base_url": "https://local.example/v1",
                }
            }
        }
    )
    registry = ProviderRegistry(config)

    first = registry.resolve("local")
    second = registry.resolve("local")

    assert first is second
    assert isinstance(first, OpenAICompatibleProvider)
    assert first.capabilities == ProviderCapabilities(
        tool_calling=True,
        native_structured_output=False,
        parallel_tool_calls=True,
    )

    await registry.close()

    assert first.closed is True
