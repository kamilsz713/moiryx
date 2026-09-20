"""Azure Foundry chat-completions adapter."""

from __future__ import annotations

import httpx

from moiryx.config import (
    AzureFoundryProviderConfig,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
)
from moiryx.models import ModelRequest, ProviderCapabilities
from moiryx.providers.openai_compatible import OpenAICompatibleProvider

_CAPABILITIES = ProviderCapabilities(
    tool_calling=True,
    native_structured_output=False,
    parallel_tool_calls=True,
)


class AzureFoundryProvider(OpenAICompatibleProvider):
    """Foundry endpoint semantics backed by the shared asynchronous transport."""

    __slots__ = ("_api_version",)

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(config, AzureFoundryProviderConfig):
            raise TypeError("config must be an AzureFoundryProviderConfig")
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

    def _request_params(self, request: ModelRequest) -> dict[str, str] | None:
        if self._api_version is None:
            return None
        return {"api-version": self._api_version}


__all__ = ["AzureFoundryProvider"]
