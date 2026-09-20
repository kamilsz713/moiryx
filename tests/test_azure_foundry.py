"""Mock-transport coverage for the Azure Foundry adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from moiryx.config import AzureFoundryProviderConfig
from moiryx.messages import UserMessage
from moiryx.models import ModelRequest, ProviderCapabilities
from moiryx.providers import AzureFoundryProvider, OpenAICompatibleProvider


def _config(
    *,
    api_version: str | None = "2024-05-01-preview",
    api_key: str | None = None,
    headers: dict[str, str] | None = None,
) -> AzureFoundryProviderConfig:
    payload: dict[str, object] = {
        "type": "azure_foundry",
        "endpoint": "https://foundry.example/models",
    }
    if api_version is not None:
        payload["api_version"] = api_version
    if api_key is not None:
        payload["api_key"] = api_key
    if headers is not None:
        payload["headers"] = headers
    return AzureFoundryProviderConfig.model_validate(payload)


def _success() -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": "foundry text"},
                "finish_reason": "stop",
            }
        ]
    }


@pytest.mark.asyncio
async def test_foundry_keeps_model_in_body_and_uses_endpoint_semantics() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_success())

    provider = AzureFoundryProvider(
        _config(api_key="foundry-key", headers={"X-Region": "west-europe"}),
        transport=httpx.MockTransport(handler),
    )

    response = await provider.complete(
        ModelRequest(
            model="mistral/deployment",
            messages=[UserMessage("Hello")],
        )
    )
    await provider.close()

    assert isinstance(provider, OpenAICompatibleProvider)
    assert str(captured[0].url) == (
        "https://foundry.example/models/chat/completions?api-version=2024-05-01-preview"
    )
    assert captured[0].headers["api-key"] == "foundry-key"
    assert captured[0].headers["X-Region"] == "west-europe"
    assert json.loads(captured[0].content) == {
        "model": "mistral/deployment",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    assert response.content == "foundry text"


@pytest.mark.asyncio
async def test_optional_version_is_omitted_and_bearer_auth_is_preserved() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_success())

    provider = AzureFoundryProvider(
        _config(
            api_version=None,
            api_key="unused-key",
            headers={"Authorization": "Bearer entra-token"},
        ),
        transport=httpx.MockTransport(handler),
    )

    await provider.complete(ModelRequest(model="deployment", messages=[]))
    await provider.close()

    assert str(captured[0].url) == ("https://foundry.example/models/chat/completions")
    assert captured[0].headers["Authorization"] == "Bearer entra-token"
    assert "api-key" not in captured[0].headers


def test_foundry_capabilities_are_explicit() -> None:
    provider = AzureFoundryProvider(_config())

    assert provider.capabilities == ProviderCapabilities(
        tool_calling=True,
        native_structured_output=False,
        parallel_tool_calls=True,
    )

    import asyncio

    asyncio.run(provider.close())
