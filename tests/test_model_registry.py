"""Tests for logical model alias resolution."""

import pytest

from moiryx.config import MoiryxConfig
from moiryx.errors import ProviderNotFoundError, UnknownModelError
from moiryx.model_registry import ModelRegistry
from moiryx.models import GenerationOptions


def _config() -> MoiryxConfig:
    return MoiryxConfig.model_validate(
        {
            "providers": {
                "router": {"type": "openrouter"},
            },
            "models": {
                "reviewer": {
                    "provider": "router",
                    "model": "vendor/model-with/slashes",
                    "generation": {"temperature": 0.2},
                    "provider_options": {"reasoning_effort": "high"},
                }
            },
        }
    )


@pytest.mark.acceptance
def test_resolve_preserves_provider_model_generation_and_options() -> None:
    resolved = ModelRegistry(_config()).resolve("reviewer")

    assert resolved.alias == "reviewer"
    assert resolved.provider == "router"
    assert resolved.model == "vendor/model-with/slashes"
    assert resolved.generation == GenerationOptions(temperature=0.2)
    assert resolved.provider_options == {"reasoning_effort": "high"}


def test_resolved_provider_options_do_not_mutate_config() -> None:
    config = _config()
    resolved = ModelRegistry(config).resolve("reviewer")

    with pytest.raises(TypeError):
        resolved.provider_options["reasoning_effort"] = "low"  # type: ignore[index]

    assert config.models["reviewer"].provider_options == {"reasoning_effort": "high"}


def test_unknown_model_alias_has_specific_error() -> None:
    with pytest.raises(UnknownModelError, match="model=missing"):
        ModelRegistry(_config()).resolve("missing")


def test_missing_provider_is_rejected_during_config_loading() -> None:
    with pytest.raises(ProviderNotFoundError, match="provider=missing"):
        MoiryxConfig.model_validate(
            {
                "models": {
                    "reviewer": {
                        "provider": "missing",
                        "model": "vendor/model",
                    }
                }
            }
        )
