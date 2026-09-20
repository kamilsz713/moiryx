"""Provider registry infrastructure; concrete adapters are added separately."""

from moiryx.providers.azure_foundry import AzureFoundryProvider
from moiryx.providers.azure_openai import AzureOpenAIProvider
from moiryx.providers.fake import ScriptedFakeProvider, ScriptedItem
from moiryx.providers.openai_compatible import (
    OpenAICompatibleProvider,
    build_openai_request,
    normalize_openai_response,
)
from moiryx.providers.openrouter import (
    DEFAULT_OPENROUTER_BASE_URL,
    OpenRouterProvider,
)
from moiryx.providers.registry import (
    PROVIDER_FACTORIES,
    ProviderAdapter,
    ProviderClient,
    ProviderFactory,
    ProviderRegistry,
    create_provider,
)
from moiryx.providers.vertex_ai import (
    VertexAIProvider,
    build_vertex_request,
    normalize_vertex_response,
)

PROVIDER_FACTORIES.setdefault("openai_compatible", OpenAICompatibleProvider)
PROVIDER_FACTORIES.setdefault("openrouter", OpenRouterProvider)
PROVIDER_FACTORIES.setdefault("azure_openai", AzureOpenAIProvider)
PROVIDER_FACTORIES.setdefault("azure_foundry", AzureFoundryProvider)
PROVIDER_FACTORIES.setdefault("vertex_ai", VertexAIProvider)

__all__ = [
    "DEFAULT_OPENROUTER_BASE_URL",
    "PROVIDER_FACTORIES",
    "AzureFoundryProvider",
    "AzureOpenAIProvider",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
    "ProviderAdapter",
    "ProviderClient",
    "ProviderFactory",
    "ProviderRegistry",
    "ScriptedFakeProvider",
    "ScriptedItem",
    "VertexAIProvider",
    "build_openai_request",
    "build_vertex_request",
    "create_provider",
    "normalize_openai_response",
    "normalize_vertex_response",
]
