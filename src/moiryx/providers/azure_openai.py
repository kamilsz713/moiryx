"""Azure OpenAI adapter using deployment-based chat-completion routes."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from moiryx.config import (
    AzureOpenAIProviderConfig,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
)
from moiryx.models import JsonObject, ModelRequest, ProviderCapabilities
from moiryx.providers.openai_compatible import (
    OpenAICompatibleProvider,
    build_openai_request,
)

_CAPABILITIES = ProviderCapabilities(
    tool_calling=True,
    native_structured_output=False,
    parallel_tool_calls=True,
)


class AzureOpenAIProvider(OpenAICompatibleProvider):
    """Azure OpenAI semantics backed by the shared asynchronous transport."""

    __slots__ = ("_api_version",)

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(config, AzureOpenAIProviderConfig):
            raise TypeError("config must be an AzureOpenAIProviderConfig")
        compatible_config = OpenAICompatibleProviderConfig(
            type="openai_compatible",
            base_url=config.endpoint,
            timeout_seconds=config.timeout_seconds,
            api_key=config.api_key,
            headers=dict(config.headers),
            capabilities=config.capabilities,
        )
        super().__init__(
            compatible_config,
            transport=transport,
            api_key_header="api-key",
            api_key_prefix="",
            alternate_auth_headers=("Authorization",),
        )
        self._api_version = config.api_version

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    def _request_path(self, request: ModelRequest) -> str:
        deployment = quote(request.model, safe="")
        return f"openai/deployments/{deployment}/chat/completions"

    def _request_params(self, request: ModelRequest) -> dict[str, str]:
        return {"api-version": self._api_version}

    def _request_payload(self, request: ModelRequest) -> JsonObject:
        payload = build_openai_request(request)
        payload.pop("model", None)
        return payload


__all__ = ["AzureOpenAIProvider"]
