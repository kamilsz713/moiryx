"""Discovery, interpolation, and validation for ``moiryx.yaml``."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self, TypeAlias

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

from moiryx.errors import ConfigurationError, ProviderNotFoundError
from moiryx.models import GenerationOptions
from moiryx.redaction import is_sensitive_key, redact

CONFIG_ENV_VAR = "MOIRYX_CONFIG"
DEFAULT_CONFIG_FILE = "moiryx.yaml"
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

PositiveNumber: TypeAlias = Annotated[int | float, Field(gt=0)]
PositiveInt: TypeAlias = Annotated[int, Field(gt=0)]
NonNegativeInt: TypeAlias = Annotated[int, Field(ge=0)]
NonNegativeFloat: TypeAlias = Annotated[float, Field(ge=0)]
Probability: TypeAlias = Annotated[float, Field(gt=0, le=1)]
NonEmptyStr: TypeAlias = Annotated[str, Field(min_length=1)]
ProviderType: TypeAlias = Literal[
    "openai_compatible",
    "openrouter",
    "azure_openai",
    "azure_foundry",
    "vertex_ai",
]


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    def __repr__(self) -> str:
        values = redact(self.model_dump())
        return f"{type(self).__name__}({values!r})"

    __str__ = __repr__


class CapabilityOverrides(_ConfigModel):
    """Optional capability overrides for non-standard provider endpoints."""

    tool_calling: bool | None = None
    native_structured_output: bool | None = None
    parallel_tool_calls: bool | None = None


class _ProviderConfig(_ConfigModel):
    timeout_seconds: PositiveNumber = 180
    api_key: SecretStr | None = None
    headers: dict[str, str | SecretStr] = Field(default_factory=dict)
    capabilities: CapabilityOverrides = Field(default_factory=CapabilityOverrides)

    @field_validator("headers", mode="before")
    @classmethod
    def _protect_sensitive_headers(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        return {
            key: SecretStr(item)
            if is_sensitive_key(key) and isinstance(item, str)
            else item
            for key, item in value.items()
        }


class OpenAICompatibleProviderConfig(_ProviderConfig):
    type: Literal["openai_compatible"]
    base_url: NonEmptyStr


class OpenRouterProviderConfig(_ProviderConfig):
    type: Literal["openrouter"]
    base_url: NonEmptyStr | None = None


class AzureOpenAIProviderConfig(_ProviderConfig):
    type: Literal["azure_openai"]
    endpoint: NonEmptyStr
    api_version: NonEmptyStr


class AzureFoundryProviderConfig(_ProviderConfig):
    type: Literal["azure_foundry"]
    endpoint: NonEmptyStr
    api_version: NonEmptyStr | None = None


class VertexAIProviderConfig(_ProviderConfig):
    type: Literal["vertex_ai"]
    project: NonEmptyStr
    location: NonEmptyStr


ProviderConfig: TypeAlias = Annotated[
    OpenAICompatibleProviderConfig
    | OpenRouterProviderConfig
    | AzureOpenAIProviderConfig
    | AzureFoundryProviderConfig
    | VertexAIProviderConfig,
    Field(discriminator="type"),
]


class _GenerationConfig(_ConfigModel):
    temperature: NonNegativeFloat | None = None
    max_tokens: PositiveInt | None = None
    top_p: Probability | None = None
    seed: int | None = None

    def to_options(self) -> GenerationOptions:
        return GenerationOptions(**self.model_dump())


def _validated_generation(value: object) -> object:
    if isinstance(value, GenerationOptions):
        return value
    if not isinstance(value, Mapping):
        return value
    try:
        return _GenerationConfig.model_validate(value).to_options()
    except ValidationError as error:
        raise ValueError(_validation_summary(error)) from None


class ModelConfig(_ConfigModel):
    """A logical model alias resolved to a provider and opaque model ID."""

    provider: NonEmptyStr
    model: NonEmptyStr
    generation: GenerationOptions = Field(default_factory=GenerationOptions)
    provider_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("generation", mode="before")
    @classmethod
    def _validate_generation(cls, value: object) -> object:
        return _validated_generation(value)


class RuntimeConfig(_ConfigModel):
    """Validated runtime limits and safety defaults."""

    default_max_steps: PositiveInt = 20
    provider_retry_attempts: NonNegativeInt = 3
    structured_output_retries: NonNegativeInt = 2
    tool_call_repair_attempts: NonNegativeInt = 2
    tool_timeout_seconds: PositiveNumber = 60
    workspace_root: Path = Path(".")
    allow_paths_outside_workspace: bool = False
    max_tool_output_chars: PositiveInt = 50_000
    generation: GenerationOptions = Field(default_factory=GenerationOptions)

    @field_validator("workspace_root", mode="before")
    @classmethod
    def _parse_workspace_root(cls, value: object) -> object:
        return Path(value) if isinstance(value, str) else value

    @field_validator("generation", mode="before")
    @classmethod
    def _validate_generation(cls, value: object) -> object:
        return _validated_generation(value)


class LoggingConfig(_ConfigModel):
    """Minimal logging and optional trace configuration."""

    level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    trace_dir: Path | None = None
    include_raw_response: bool = False

    @field_validator("trace_dir", mode="before")
    @classmethod
    def _parse_trace_dir(cls, value: object) -> object:
        return Path(value) if isinstance(value, str) else value


class MoiryxConfig(_ConfigModel):
    """Validated global configuration for Moiryx."""

    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    tool_modules: list[str] = Field(default_factory=list)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @model_validator(mode="after")
    def _validate_model_provider_references(self) -> Self:
        for model_alias, model in self.models.items():
            if model.provider not in self.providers:
                raise ProviderNotFoundError(
                    "Model references a provider that is not configured",
                    model_alias=model_alias,
                    provider_name=model.provider,
                )
        return self


def discover_config_path(
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Path:
    """Return the first existing config path in the documented search order."""
    environment = os.environ if environ is None else environ
    working_directory = Path.cwd() if cwd is None else cwd
    candidates: list[Path] = []

    override = environment.get(CONFIG_ENV_VAR)
    if override:
        override_path = Path(override)
        if not override_path.is_absolute():
            override_path = working_directory / override_path
        candidates.append(override_path.resolve())

    default_path = (working_directory / DEFAULT_CONFIG_FILE).resolve()
    if default_path not in candidates:
        candidates.append(default_path)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    searched = ", ".join(str(candidate) for candidate in candidates)
    raise ConfigurationError(f"Configuration file not found; searched: {searched}")


def interpolate_env(
    value: object,
    *,
    environ: Mapping[str, str] | None = None,
) -> object:
    """Recursively interpolate ``${NAME}`` in string values of dicts and lists."""
    environment = os.environ if environ is None else environ

    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in environment:
                raise ConfigurationError(
                    f"Required environment variable '{name}' is not set"
                )
            return environment[name]

        return _ENV_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [interpolate_env(item, environ=environment) for item in value]
    if isinstance(value, Mapping):
        return {
            key: interpolate_env(item, environ=environment)
            for key, item in value.items()
        }
    return value


def _validation_summary(error: ValidationError) -> str:
    issues: list[str] = []
    for item in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = ".".join(str(part) for part in item["loc"])
        prefix = f"{location}: " if location else ""
        issues.append(f"{prefix}{item['msg']}")
    return "; ".join(issues)


def _read_config(path: Path) -> MoiryxConfig:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(
            f"Could not read configuration file '{path}': {type(error).__name__}"
        ) from error

    try:
        loaded: object = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = (
            f" at line {mark.line + 1}, column {mark.column + 1}"
            if mark is not None
            else ""
        )
        raise ConfigurationError(
            f"Invalid YAML in configuration file '{path}'{location}"
        ) from error

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, Mapping):
        raise ConfigurationError(f"Configuration root in '{path}' must be a mapping")

    interpolated = interpolate_env(loaded)
    try:
        return MoiryxConfig.model_validate(interpolated)
    except ValidationError as error:
        raise ConfigurationError(
            f"Invalid configuration in '{path}': {_validation_summary(error)}"
        ) from error


@lru_cache(maxsize=1)
def _load_cached_config() -> MoiryxConfig:
    return _read_config(discover_config_path())


def load_config() -> MoiryxConfig:
    """Discover, validate, and cache the global configuration."""
    return _load_cached_config()


def reset_config_cache() -> None:
    """Clear the process-local config cache, primarily for controlled reloads."""
    _load_cached_config.cache_clear()


__all__ = [
    "CONFIG_ENV_VAR",
    "DEFAULT_CONFIG_FILE",
    "AzureFoundryProviderConfig",
    "AzureOpenAIProviderConfig",
    "CapabilityOverrides",
    "LoggingConfig",
    "ModelConfig",
    "MoiryxConfig",
    "OpenAICompatibleProviderConfig",
    "OpenRouterProviderConfig",
    "ProviderConfig",
    "ProviderType",
    "RuntimeConfig",
    "VertexAIProviderConfig",
    "discover_config_path",
    "interpolate_env",
    "load_config",
    "reset_config_cache",
]
