"""Mock-transport coverage for the OpenRouter provider specialization."""

from __future__ import annotations

import json

import httpx
import pytest

from moiryx.config import MoiryxConfig, OpenRouterProviderConfig
from moiryx.messages import UserMessage
from moiryx.models import ModelRequest, ProviderCapabilities, Usage
from moiryx.providers import (
    DEFAULT_OPENROUTER_BASE_URL,
    OpenAICompatibleProvider,
    OpenRouterProvider,
    ProviderRegistry,
)


def _config(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    headers: dict[str, str] | None = None,
) -> OpenRouterProviderConfig:
    payload: dict[str, object] = {"type": "openrouter"}
    if base_url is not None:
        payload["base_url"] = base_url
    if api_key is not None:
        payload["api_key"] = api_key
    if headers is not None:
        payload["headers"] = headers
    return OpenRouterProviderConfig.model_validate(payload)


def _success(*, usage: object = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "routed"},
                "finish_reason": "stop",
            }
        ]
    }
    if usage is not None:
        payload["usage"] = usage
    return payload


@pytest.mark.asyncio
async def test_defaults_headers_and_slash_model_use_shared_transport() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_success())

    api_key = "sentinel-openrouter-key"
    custom_secret = "sentinel-custom-header"
    config = _config(
        api_key=api_key,
        headers={
            "HTTP-Referer": "https://moiryx.example",
            "X-OpenRouter-Title": "Moiryx",
            "X-Client-Secret": custom_secret,
        },
    )
    provider = OpenRouterProvider(
        config,
        transport=httpx.MockTransport(handler),
    )

    response = await provider.complete(
        ModelRequest(
            model="anthropic/claude-sonnet-4.5",
            messages=[UserMessage("Hello")],
        )
    )
    await provider.close()

    assert response.content == "routed"
    assert isinstance(provider, OpenAICompatibleProvider)
    assert str(captured[0].url) == (f"{DEFAULT_OPENROUTER_BASE_URL}/chat/completions")
    assert captured[0].headers["Authorization"] == f"Bearer {api_key}"
    assert captured[0].headers["HTTP-Referer"] == "https://moiryx.example"
    assert captured[0].headers["X-OpenRouter-Title"] == "Moiryx"
    assert captured[0].headers["X-Client-Secret"] == custom_secret
    assert json.loads(captured[0].content)["model"] == ("anthropic/claude-sonnet-4.5")
    assert api_key not in repr(config)
    assert custom_secret not in repr(config)
    assert api_key not in repr(provider)
    assert custom_secret not in repr(provider)


@pytest.mark.asyncio
async def test_custom_base_url_and_usage_cost_are_normalized() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json=_success(
                usage={
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "total_tokens": 16,
                    "cost": 0.00125,
                }
            ),
        )

    provider = OpenRouterProvider(
        _config(base_url="https://router.example/openai/v1/"),
        transport=httpx.MockTransport(handler),
    )
    response = await provider.complete(ModelRequest(model="vendor/model", messages=[]))
    await provider.close()

    assert str(captured[0].url) == ("https://router.example/openai/v1/chat/completions")
    assert response.usage == Usage(
        input_tokens=12,
        output_tokens=4,
        total_tokens=16,
        cost=0.00125,
    )


@pytest.mark.asyncio
async def test_missing_usage_and_cost_remain_unknown_instead_of_zero() -> None:
    responses = iter(
        [
            httpx.Response(200, json=_success()),
            httpx.Response(
                200,
                json=_success(
                    usage={
                        "prompt_tokens": 2,
                        "completion_tokens": 3,
                        "total_tokens": 5,
                    }
                ),
            ),
        ]
    )
    provider = OpenRouterProvider(
        _config(),
        transport=httpx.MockTransport(lambda request: next(responses)),
    )

    without_usage = await provider.complete(
        ModelRequest(model="vendor/model", messages=[])
    )
    without_cost = await provider.complete(
        ModelRequest(model="vendor/model", messages=[])
    )
    await provider.close()

    assert without_usage.usage is None
    assert without_cost.usage == Usage(
        input_tokens=2,
        output_tokens=3,
        total_tokens=5,
        cost=None,
    )


@pytest.mark.asyncio
async def test_default_factory_is_registered_with_explicit_capabilities() -> None:
    registry = ProviderRegistry(
        MoiryxConfig.model_validate({"providers": {"router": {"type": "openrouter"}}})
    )

    provider = registry.resolve("router")

    assert isinstance(provider, OpenRouterProvider)
    assert provider.capabilities == ProviderCapabilities(
        tool_calling=True,
        native_structured_output=False,
        parallel_tool_calls=True,
    )

    await registry.close()
