"""Provider-agnostic data contracts shared by the Moiryx core."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from pydantic import BaseModel, TypeAdapter

from moiryx.messages import Message, RawArguments, ToolCall

JsonObject: TypeAlias = dict[str, Any]


@dataclass(frozen=True, slots=True)
class GenerationOptions:
    """Generation settings supported consistently across providers."""

    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    seed: int | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    """Normalized token and optional cost information."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Features that an adapter can guarantee."""

    tool_calling: bool = False
    native_structured_output: bool = False
    parallel_tool_calls: bool = False


@dataclass(slots=True)
class ToolSchema:
    """Provider-neutral function schema exposed to a model."""

    name: str
    description: str
    parameters: JsonObject


@dataclass(slots=True)
class ToolDefinition:
    """Runtime metadata derived from a decorated Python function."""

    name: str
    description: str
    function: Callable[..., Any]
    input_model: type[BaseModel]
    return_adapter: TypeAdapter[Any] | None = None

    @property
    def schema(self) -> ToolSchema:
        """Return the provider-neutral schema generated from the input model."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=self.input_model.model_json_schema(),
        )


@dataclass(slots=True)
class ModelRequest:
    """A normalized request accepted by every provider adapter."""

    model: str
    messages: list[Message]
    tools: list[ToolSchema] = field(default_factory=list)
    output_schema: JsonObject | None = None
    generation: GenerationOptions = field(default_factory=GenerationOptions)


@dataclass(slots=True)
class ModelResponse:
    """A normalized provider response used by the shared runtime."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    structured_output: JsonObject | None = None
    finish_reason: str | None = None
    usage: Usage | None = None
    raw: Any | None = field(default=None, repr=False, compare=False)


__all__ = [
    "GenerationOptions",
    "JsonObject",
    "ModelRequest",
    "ModelResponse",
    "ProviderCapabilities",
    "RawArguments",
    "ToolCall",
    "ToolDefinition",
    "ToolSchema",
    "Usage",
]
