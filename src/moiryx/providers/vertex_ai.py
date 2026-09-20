"""Google Vertex AI adapter backed by the optional Google Gen AI SDK."""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib import import_module
from typing import Any, Protocol, cast

from pydantic import BaseModel

from moiryx.config import ProviderConfig, VertexAIProviderConfig
from moiryx.errors import ConfigurationError, ProviderRequestError
from moiryx.messages import (
    AssistantMessage,
    RepairMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from moiryx.models import (
    JsonObject,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    Usage,
)

_CAPABILITIES = ProviderCapabilities(
    tool_calling=True,
    native_structured_output=True,
    parallel_tool_calls=True,
)


class VertexModelsClient(Protocol):
    """Minimal async SDK surface used by the adapter."""

    async def generate_content(
        self,
        *,
        model: str,
        contents: list[JsonObject],
        config: JsonObject,
    ) -> object: ...


class VertexAsyncClient(Protocol):
    """Injectable async client contract for credential-free tests."""

    models: VertexModelsClient

    async def aclose(self) -> None: ...


def _field(value: object, *names: str) -> object | None:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return cast(object, value[name])
        candidate = cast(object, getattr(value, name, None))
        if candidate is not None:
            return candidate
    return None


def _items(value: object) -> list[object]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _string_value(value: object) -> str | None:
    if isinstance(value, str):
        return value
    enum_value = getattr(value, "value", None)
    return enum_value if isinstance(enum_value, str) else None


def _tool_arguments(
    value: object,
) -> tuple[
    dict[str, Any] | None,
    str | dict[str, Any] | None,
    str | None,
]:
    if isinstance(value, Mapping):
        copied = dict(value)
        return copied, copied, None
    if isinstance(value, str):
        try:
            parsed: object = json.loads(value)
        except json.JSONDecodeError as error:
            return None, value, f"invalid JSON at character {error.pos}"
        if isinstance(parsed, Mapping):
            copied = dict(parsed)
            return copied, value, None
        return None, value, "arguments must decode to a JSON object"
    return None, None, "arguments are missing"


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        return _jsonable(dumped)
    return {"type": type(value).__name__}


def _message_parts(message: AssistantMessage) -> list[JsonObject]:
    parts: list[JsonObject] = []
    if message.content is not None:
        parts.append({"text": message.content})
    for call in message.tool_calls:
        arguments = call.arguments if call.arguments is not None else {}
        function_call: JsonObject = {
            "name": call.name,
            "args": arguments,
        }
        if call.id:
            function_call["id"] = call.id
        parts.append({"function_call": function_call})
    return parts


def _tool_output(content: str) -> object:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content


def build_vertex_request(request: ModelRequest) -> tuple[list[JsonObject], JsonObject]:
    """Translate a normalized request to Google Gen AI SDK dictionaries."""
    contents: list[JsonObject] = []
    system_instructions: list[str] = []
    for message in request.messages:
        if isinstance(message, (SystemMessage, RepairMessage)):
            system_instructions.append(message.content)
        elif isinstance(message, UserMessage):
            contents.append({"role": "user", "parts": [{"text": message.content}]})
        elif isinstance(message, AssistantMessage):
            contents.append({"role": "model", "parts": _message_parts(message)})
        elif isinstance(message, ToolMessage):
            function_response: JsonObject = {
                "name": message.name,
                "response": {"output": _tool_output(message.content)},
            }
            if message.tool_call_id:
                function_response["id"] = message.tool_call_id
            contents.append(
                {
                    "role": "tool",
                    "parts": [{"function_response": function_response}],
                }
            )

    config: JsonObject = {}
    if system_instructions:
        config["system_instruction"] = "\n\n".join(system_instructions)
    if request.tools:
        config["tools"] = [
            {
                "function_declarations": [
                    {
                        "name": schema.name,
                        "description": schema.description,
                        "parameters_json_schema": schema.parameters,
                    }
                    for schema in request.tools
                ]
            }
        ]
    generation_values = (
        ("temperature", request.generation.temperature),
        ("max_output_tokens", request.generation.max_tokens),
        ("top_p", request.generation.top_p),
        ("seed", request.generation.seed),
    )
    for name, value in generation_values:
        if value is not None:
            config[name] = value
    if request.output_schema is not None:
        config["response_mime_type"] = "application/json"
        config["response_json_schema"] = request.output_schema
    return contents, config


def normalize_vertex_response(
    response: object,
    *,
    expect_structured_output: bool = False,
) -> ModelResponse:
    """Normalize one Google Gen AI SDK response without leaking SDK types."""
    candidates = _items(_field(response, "candidates"))
    if not candidates:
        raise ProviderRequestError(
            "Vertex AI returned a response without candidates",
            retryable=False,
        )
    candidate = candidates[0]
    content = _field(candidate, "content")
    parts = _items(_field(content, "parts"))
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for index, part in enumerate(parts):
        text = _field(part, "text")
        if isinstance(text, str):
            text_parts.append(text)
        function_call = _field(part, "function_call", "functionCall")
        if function_call is None:
            continue
        name_value = _field(function_call, "name")
        name = name_value if isinstance(name_value, str) else ""
        identifier = _field(function_call, "id")
        call_id = (
            identifier
            if isinstance(identifier, str) and identifier
            else f"vertex-call-{index}"
        )
        arguments, raw_arguments, parse_error = _tool_arguments(
            _field(function_call, "args")
        )
        tool_calls.append(
            ToolCall(
                id=call_id,
                name=name,
                arguments=arguments,
                raw_arguments=raw_arguments,
                parse_error=parse_error,
            )
        )

    usage_value = _field(response, "usage_metadata", "usageMetadata")
    usage = None
    if usage_value is not None:
        usage = Usage(
            input_tokens=_optional_int(
                _field(usage_value, "prompt_token_count", "promptTokenCount")
            ),
            output_tokens=_optional_int(
                _field(usage_value, "candidates_token_count", "candidatesTokenCount")
            ),
            total_tokens=_optional_int(
                _field(usage_value, "total_token_count", "totalTokenCount")
            ),
        )

    structured_output = None
    if expect_structured_output:
        parsed = _field(response, "parsed")
        if isinstance(parsed, BaseModel):
            structured_output = parsed.model_dump(mode="json")
        elif isinstance(parsed, Mapping):
            structured_output = dict(parsed)
        elif text_parts:
            try:
                decoded: object = json.loads("".join(text_parts))
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, Mapping):
                structured_output = dict(decoded)

    finish_reason = _string_value(_field(candidate, "finish_reason", "finishReason"))
    return ModelResponse(
        content="".join(text_parts) if text_parts else None,
        tool_calls=tool_calls,
        structured_output=structured_output,
        finish_reason=finish_reason,
        usage=usage,
        raw=_jsonable(response),
    )


def _default_client(config: VertexAIProviderConfig) -> VertexAsyncClient:
    try:
        genai: Any = import_module("google.genai")
    except ImportError as error:
        raise ConfigurationError(
            "Vertex AI requires the optional 'google' extra; install 'moiryx[google]'"
        ) from error
    owner: Any = genai.Client(
        vertexai=True,
        project=config.project,
        location=config.location,
        http_options={"api_version": "v1"},
    )
    return cast(VertexAsyncClient, owner.aio)


class VertexAIProvider:
    """Asynchronous Vertex AI adapter using ADC or service-account environment."""

    __slots__ = ("_client", "_closed")

    def __init__(
        self,
        config: ProviderConfig,
        *,
        client: VertexAsyncClient | None = None,
    ) -> None:
        if not isinstance(config, VertexAIProviderConfig):
            raise TypeError("config must be a VertexAIProviderConfig")
        if config.api_key is not None or config.headers:
            raise ConfigurationError(
                "Vertex AI uses Application Default Credentials; api_key and "
                "custom headers are not supported"
            )
        self._client = client or _default_client(config)
        self._closed = False

    def __repr__(self) -> str:
        return f"{type(self).__name__}(closed={self._closed!r})"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    @property
    def closed(self) -> bool:
        return self._closed

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if self._closed:
            raise ProviderRequestError("Provider client is closed", retryable=False)
        contents, generation_config = build_vertex_request(request)
        try:
            response = await self._client.models.generate_content(
                model=request.model,
                contents=contents,
                config=generation_config,
            )
        except TimeoutError:
            raise
        except Exception as error:
            status = getattr(error, "status_code", None)
            status_code = (
                status
                if isinstance(status, int) and not isinstance(status, bool)
                else None
            )
            raise ProviderRequestError(
                f"Vertex AI request failed with {type(error).__name__}",
                status_code=status_code,
                retryable=status_code is None
                or status_code in {429, 500, 502, 503, 504},
            ) from error
        return normalize_vertex_response(
            response,
            expect_structured_output=request.output_schema is not None,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._client.aclose()


__all__ = [
    "VertexAIProvider",
    "VertexAsyncClient",
    "VertexModelsClient",
    "build_vertex_request",
    "normalize_vertex_response",
]
