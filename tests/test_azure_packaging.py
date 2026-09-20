"""Credential-free provider matrix and packaging checks for Azure adapters."""

from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

import pytest

from moiryx.config import MoiryxConfig
from moiryx.providers import (
    AzureFoundryProvider,
    AzureOpenAIProvider,
    ProviderRegistry,
)


@pytest.mark.parametrize(
    ("alias", "payload", "provider_type"),
    [
        (
            "azure",
            {
                "type": "azure_openai",
                "endpoint": "https://azure.example",
                "api_version": "2025-04-01-preview",
            },
            AzureOpenAIProvider,
        ),
        (
            "foundry",
            {
                "type": "azure_foundry",
                "endpoint": "https://foundry.example/models",
            },
            AzureFoundryProvider,
        ),
    ],
)
def test_default_factory_matrix_needs_no_credentials(
    alias: str,
    payload: dict[str, str],
    provider_type: type[AzureOpenAIProvider] | type[AzureFoundryProvider],
) -> None:
    registry = ProviderRegistry(
        MoiryxConfig.model_validate({"providers": {alias: payload}})
    )

    provider = registry.resolve(alias)

    assert isinstance(provider, provider_type)
    asyncio.run(registry.close())


def test_azure_extra_has_no_unused_sdk_dependency() -> None:
    project_root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((project_root / "pyproject.toml").read_text("utf-8"))
    project = metadata["project"]
    core_dependencies = project["dependencies"]
    extras = project["optional-dependencies"]

    assert extras["azure"] == []
    assert not any(
        dependency.lower().startswith(("azure-", "openai"))
        for dependency in core_dependencies
    )
