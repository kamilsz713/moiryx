"""Provider factory lookup, instance caching, and lifecycle management."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, TypeAlias, runtime_checkable

from moiryx.config import MoiryxConfig, ProviderConfig, ProviderType
from moiryx.errors import ConfigurationError, ProviderNotFoundError
from moiryx.models import ModelRequest, ModelResponse, ProviderCapabilities


@runtime_checkable
class ProviderAdapter(Protocol):
    """Provider-neutral asynchronous model adapter contract."""

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Return the features guaranteed by this provider adapter."""
        ...

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Complete one normalized request without leaking SDK types."""
        ...

    async def close(self) -> None:
        """Release resources owned by the provider client."""
        ...


ProviderClient: TypeAlias = ProviderAdapter
ProviderFactory: TypeAlias = Callable[[ProviderConfig], ProviderAdapter]

PROVIDER_FACTORIES: dict[ProviderType, ProviderFactory] = {}


def create_provider(
    config: ProviderConfig,
    *,
    factories: Mapping[ProviderType, ProviderFactory] | None = None,
    provider_name: str | None = None,
) -> ProviderAdapter:
    """Create one provider from its explicit, validated type."""
    available_factories = PROVIDER_FACTORIES if factories is None else factories
    factory = available_factories.get(config.type)
    if factory is None:
        raise ConfigurationError(
            f"No provider adapter factory is registered for type '{config.type}'",
            provider_name=provider_name,
        )
    return factory(config)


class ProviderRegistry:
    """Resolve and optionally cache provider clients by configured alias."""

    def __init__(
        self,
        config: MoiryxConfig,
        *,
        factories: Mapping[ProviderType, ProviderFactory] | None = None,
        cache_instances: bool = True,
    ) -> None:
        self._configs = dict(config.providers)
        self._factories = dict(PROVIDER_FACTORIES if factories is None else factories)
        self._cache_instances = cache_instances
        self._instances: dict[str, ProviderAdapter] = {}
        self._owned_instances: list[ProviderAdapter] = []

    def resolve(self, alias: str) -> ProviderAdapter:
        """Return the provider for an alias, reusing its cached client by default."""
        if self._cache_instances and alias in self._instances:
            return self._instances[alias]

        try:
            config = self._configs[alias]
        except KeyError:
            raise ProviderNotFoundError(
                "Provider alias is not configured",
                provider_name=alias,
            ) from None

        provider = create_provider(
            config,
            factories=self._factories,
            provider_name=alias,
        )
        self._owned_instances.append(provider)
        if self._cache_instances:
            self._instances[alias] = provider
        return provider

    async def close(self) -> None:
        """Close every cached client once and clear the cache before awaiting."""
        instances = tuple(self._owned_instances)
        self._instances.clear()
        self._owned_instances.clear()
        seen: set[int] = set()
        for provider in instances:
            identity = id(provider)
            if identity in seen:
                continue
            seen.add(identity)
            await provider.close()


__all__ = [
    "PROVIDER_FACTORIES",
    "ProviderAdapter",
    "ProviderClient",
    "ProviderFactory",
    "ProviderRegistry",
    "create_provider",
]
