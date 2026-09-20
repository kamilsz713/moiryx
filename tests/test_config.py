"""Tests for configuration discovery, interpolation, and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from moiryx.config import (
    CONFIG_ENV_VAR,
    MoiryxConfig,
    OpenAICompatibleProviderConfig,
    discover_config_path,
    interpolate_env,
    load_config,
    reset_config_cache,
)
from moiryx.errors import ConfigurationError


@pytest.fixture(autouse=True)
def clear_config_cache() -> None:
    reset_config_cache()
    yield
    reset_config_cache()


def _write_config(path: Path, *, max_steps: int = 20) -> None:
    path.write_text(
        "\n".join(
            (
                "providers:",
                "  local:",
                "    type: openai_compatible",
                "    base_url: http://localhost:8080/v1",
                "runtime:",
                f"  default_max_steps: {max_steps}",
            )
        ),
        encoding="utf-8",
    )


def test_environment_config_takes_precedence(tmp_path: Path) -> None:
    default_path = tmp_path / "moiryx.yaml"
    override_path = tmp_path / "override.yaml"
    _write_config(default_path, max_steps=10)
    _write_config(override_path, max_steps=30)

    discovered = discover_config_path(
        environ={CONFIG_ENV_VAR: str(override_path)}, cwd=tmp_path
    )

    assert discovered == override_path.resolve()


def test_missing_config_lists_every_searched_location(tmp_path: Path) -> None:
    override_path = tmp_path / "missing-override.yaml"

    with pytest.raises(ConfigurationError) as captured:
        discover_config_path(environ={CONFIG_ENV_VAR: str(override_path)}, cwd=tmp_path)

    message = str(captured.value)
    assert str(override_path.resolve()) in message
    assert str((tmp_path / "moiryx.yaml").resolve()) in message


def test_config_is_cached_until_explicit_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "moiryx.yaml"
    _write_config(path, max_steps=10)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)

    first = load_config()
    _write_config(path, max_steps=40)
    cached = load_config()
    reset_config_cache()
    reloaded = load_config()

    assert cached is first
    assert cached.runtime.default_max_steps == 10
    assert reloaded.runtime.default_max_steps == 40


def test_interpolation_is_recursive_and_preserves_literals() -> None:
    source = {
        "provider": {
            "api_key": "Bearer ${TOKEN}",
            "nested": ["${ENDPOINT}/v1", 3, False, None],
        }
    }

    result = interpolate_env(
        source,
        environ={"TOKEN": "sentinel-token", "ENDPOINT": "https://local"},
    )

    assert result == {
        "provider": {
            "api_key": "Bearer sentinel-token",
            "nested": ["https://local/v1", 3, False, None],
        }
    }


def test_missing_interpolation_names_only_the_missing_variable() -> None:
    with pytest.raises(ConfigurationError) as captured:
        interpolate_env(
            {"api_key": "${PRESENT}", "endpoint": "${MISSING}"},
            environ={"PRESENT": "sentinel-secret"},
        )

    assert "MISSING" in str(captured.value)
    assert "sentinel-secret" not in str(captured.value)


def test_runtime_defaults_and_provider_types_are_validated() -> None:
    config = MoiryxConfig.model_validate(
        {
            "providers": {
                "local": {
                    "type": "openai_compatible",
                    "base_url": "http://localhost:8080/v1",
                }
            }
        }
    )

    provider = config.providers["local"]
    assert isinstance(provider, OpenAICompatibleProviderConfig)
    assert provider.timeout_seconds == 180
    assert config.runtime.default_max_steps == 20
    assert config.runtime.provider_retry_attempts == 3
    assert config.runtime.structured_output_retries == 2
    assert config.runtime.tool_call_repair_attempts == 2
    assert config.runtime.tool_timeout_seconds == 60
    assert config.runtime.workspace_root == Path(".")
    assert config.runtime.allow_paths_outside_workspace is False
    assert config.runtime.max_tool_output_chars == 50_000
    assert config.logging.include_raw_response is False


@pytest.mark.parametrize(
    "payload",
    (
        {"providers": {"bad": {"type": "unknown"}}},
        {
            "providers": {
                "local": {
                    "type": "openai_compatible",
                    "base_url": "http://localhost",
                    "timeout_seconds": "slow",
                }
            }
        },
        {"runtime": {"default_max_steps": 0}},
        {"runtime": {"provider_retry_attempts": -1}},
        {"runtime": {"tool_timeout_seconds": 0}},
        {"runtime": {"workspace_root": ["not", "a", "path"]}},
        {"runtime": {"max_tool_output_chars": 0}},
        {"runtime": {"generation": {"temperature": -0.1}}},
        {"runtime": {"generation": {"top_p": 1.1}}},
        {"runtime": {"generation": {"frequency_penalty": 0.5}}},
        {"logging": {"include_raw_response": "yes"}},
    ),
)
def test_invalid_provider_and_runtime_settings_are_rejected(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        MoiryxConfig.model_validate(payload)


def test_repr_redacts_api_keys_authorization_and_nested_secrets() -> None:
    secret = "sentinel-secret-value"
    config = MoiryxConfig.model_validate(
        {
            "providers": {
                "router": {
                    "type": "openrouter",
                    "api_key": secret,
                    "headers": {
                        "Authorization": f"Bearer {secret}",
                        "X-Title": "Moiryx tests",
                    },
                }
            },
            "models": {
                "reviewer": {
                    "provider": "router",
                    "model": "vendor/model",
                    "provider_options": {"access_token": secret},
                }
            },
        }
    )

    provider = config.providers["router"]
    rendered = repr(config)
    assert isinstance(provider.api_key, SecretStr)
    assert secret not in rendered
    assert "Bearer" not in rendered
    assert "Moiryx tests" in rendered
    assert "**********" in rendered


def test_yaml_validation_error_does_not_echo_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sentinel-secret-value"
    path = tmp_path / "moiryx.yaml"
    path.write_text(
        "\n".join(
            (
                "providers:",
                "  local:",
                "    type: openai_compatible",
                "    base_url: http://localhost",
                f"    api_key: {secret}",
                "runtime:",
                "  default_max_steps: invalid",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_ENV_VAR, str(path))

    with pytest.raises(ConfigurationError) as captured:
        load_config()

    assert "runtime.default_max_steps" in str(captured.value)
    assert secret not in str(captured.value)
