"""Resolution of logical model aliases from validated configuration."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from moiryx.config import MoiryxConfig
from moiryx.errors import ProviderNotFoundError, UnknownModelError
from moiryx.models import GenerationOptions


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    """Provider-neutral result of resolving a logical model alias."""

    alias: str
    provider: str
    model: str
    generation: GenerationOptions
    provider_options: MappingProxyType[str, Any]


class ModelRegistry:
    """Resolve configured model aliases and validate provider references."""

    def __init__(self, config: MoiryxConfig) -> None:
        self._models = dict(config.models)
        self._provider_aliases = frozenset(config.providers)
        self._validate_provider_references()

    def _validate_provider_references(self) -> None:
        for alias, model in self._models.items():
            if model.provider not in self._provider_aliases:
                raise ProviderNotFoundError(
                    "Model references a provider that is not configured",
                    model_alias=alias,
                    provider_name=model.provider,
                )

    def resolve(self, alias: str) -> ResolvedModel:
        """Resolve an alias without interpreting the provider's model ID."""
        try:
            model = self._models[alias]
        except KeyError:
            raise UnknownModelError(
                "Unknown model alias",
                model_alias=alias,
            ) from None

        return ResolvedModel(
            alias=alias,
            provider=model.provider,
            model=model.model,
            generation=model.generation,
            provider_options=MappingProxyType(deepcopy(model.provider_options)),
        )


__all__ = ["ModelRegistry", "ResolvedModel"]
