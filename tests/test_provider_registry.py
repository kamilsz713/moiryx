"""Tests for provider factory dispatch, caching, and cleanup."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from moiryx.config import MoiryxConfig, ProviderConfig
from moiryx.errors import ConfigurationError, ProviderNotFoundError
from moiryx.models import ModelRequest, ModelResponse, ProviderCapabilities
from moiryx.providers.registry import ProviderFactory, ProviderRegistry


@dataclass
class FakeProvider:
    config: ProviderConfig
    close_calls: int = 0

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise AssertionError(f"Unexpected request for {request.model}")

    async def close(self) -> None:
        self.close_calls += 1


def _config() -> MoiryxConfig:
    return MoiryxConfig.model_validate(
        {
            "providers": {
                "local": {
                    "type": "openai_compatible",
                    "base_url": "http://localhost:8080/v1",
                },
                "router": {"type": "openrouter"},
            }
        }
    )


@pytest.mark.asyncio
async def test_factory_dispatches_by_type_and_cache_is_per_alias() -> None:
    created: list[FakeProvider] = []

    def factory(config: ProviderConfig) -> FakeProvider:
        provider = FakeProvider(config)
        created.append(provider)
        return provider

    factories: dict[str, ProviderFactory] = {
        "openai_compatible": factory,
        "openrouter": factory,
    }
    registry = ProviderRegistry(_config(), factories=factories)  # type: ignore[arg-type]

    local_first = registry.resolve("local")
    local_second = registry.resolve("local")
    router = registry.resolve("router")

    assert local_first is local_second
    assert router is not local_first
    assert len(created) == 2

    await registry.close()

    assert [provider.close_calls for provider in created] == [1, 1]
    assert registry.resolve("local") is not local_first


def test_missing_factory_has_concrete_configuration_error() -> None:
    registry = ProviderRegistry(_config(), factories={})

    with pytest.raises(ConfigurationError) as captured:
        registry.resolve("local")

    assert "openai_compatible" in str(captured.value)
    assert "provider=local" in str(captured.value)


def test_unknown_provider_alias_has_specific_error() -> None:
    registry = ProviderRegistry(_config(), factories={})

    with pytest.raises(ProviderNotFoundError, match="provider=missing"):
        registry.resolve("missing")


@pytest.mark.asyncio
async def test_caching_can_be_disabled_without_losing_cleanup() -> None:
    created: list[FakeProvider] = []

    def factory(config: ProviderConfig) -> FakeProvider:
        provider = FakeProvider(config)
        created.append(provider)
        return provider

    factories: dict[str, ProviderFactory] = {"openrouter": factory}
    registry = ProviderRegistry(
        _config(),
        factories=factories,  # type: ignore[arg-type]
        cache_instances=False,
    )

    assert registry.resolve("router") is not registry.resolve("router")
    assert len(created) == 2

    await registry.close()

    assert [provider.close_calls for provider in created] == [1, 1]
