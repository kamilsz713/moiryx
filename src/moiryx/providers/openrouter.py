"""OpenRouter specialization of the OpenAI-compatible provider adapter."""

from __future__ import annotations

import httpx

from moiryx.config import (
    OpenAICompatibleProviderConfig,
    OpenRouterProviderConfig,
    ProviderConfig,
)
from moiryx.models import ProviderCapabilities
from moiryx.providers.openai_compatible import OpenAICompatibleProvider

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_CAPABILITIES = ProviderCapabilities(
    tool_calling=True,
    native_structured_output=False,
    parallel_tool_calls=True,
)


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter defaults backed by the shared chat-completions transport."""

    __slots__ = ()

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(config, OpenRouterProviderConfig):
            raise TypeError("config must be an OpenRouterProviderConfig")
        compatible_config = OpenAICompatibleProviderConfig(
            type="openai_compatible",
            base_url=config.base_url or DEFAULT_OPENROUTER_BASE_URL,
            timeout_seconds=config.timeout_seconds,
            api_key=config.api_key,
            headers=dict(config.headers),
            capabilities=config.capabilities,
        )
        super().__init__(compatible_config, transport=transport)

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES


__all__ = ["DEFAULT_OPENROUTER_BASE_URL", "OpenRouterProvider"]
