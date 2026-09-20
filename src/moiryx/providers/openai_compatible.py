"""Async adapter for the minimal OpenAI-compatible chat completions API."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, assert_never

import httpx
from pydantic import SecretStr

from moiryx.config import OpenAICompatibleProviderConfig, ProviderConfig
from moiryx.errors import ProviderRequestError
from moiryx.messages import (
    AssistantMessage,
    Message,
    RepairMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from moiryx.models import (
    GenerationOptions,
    JsonObject,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ToolSchema,
    Usage,
)

_CAPABILITIES = ProviderCapabilities(
    tool_calling=True,
    native_structured_output=False,
    parallel_tool_calls=True,
)


def _secret_value(value: str | SecretStr) -> str:
    return value.get_secret_value() if isinstance(value, SecretStr) else value


def _serialize_tool_arguments(call: ToolCall) -> str:
    raw = call.raw_arguments
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    if call.arguments is not None:
        return json.dumps(
            call.arguments,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return ""


def _serialize_message(message: Message) -> JsonObject:
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    if isinstance(message, UserMessage):
        return {"role": "user", "content": message.content}
    if isinstance(message, RepairMessage):
        return {"role": "system", "content": message.content}
    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    if isinstance(message, AssistantMessage):
        serialized: JsonObject = {"role": "assistant"}
        if message.content is not None:
            serialized["content"] = message.content
        if message.tool_calls:
            serialized["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": _serialize_tool_arguments(call),
                    },
                }
                for call in message.tool_calls
            ]
        return serialized
    assert_never(message)


def _serialize_tool_schema(schema: ToolSchema) -> JsonObject:
    return {
        "type": "function",
        "function": {
            "name": schema.name,
            "description": schema.description,
            "parameters": schema.parameters,
        },
    }


def _apply_generation(payload: JsonObject, generation: GenerationOptions) -> None:
    values = (
        ("temperature", generation.temperature),
        ("max_tokens", generation.max_tokens),
        ("top_p", generation.top_p),
        ("seed", generation.seed),
    )
    for name, value in values:
        if value is not None:
            payload[name] = value


def build_openai_request(request: ModelRequest) -> JsonObject:
    """Translate a normalized request to a minimal chat-completions payload."""
    payload: JsonObject = {
        "model": request.model,
        "messages": [_serialize_message(message) for message in request.messages],
    }
    if request.tools:
        payload["tools"] = [_serialize_tool_schema(schema) for schema in request.tools]
    if request.output_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "moiryx_result",
                "strict": True,
                "schema": request.output_schema,
            },
        }
    _apply_generation(payload, request.generation)
    return payload


def _invalid_response(detail: str) -> ProviderRequestError:
    return ProviderRequestError(
        f"Provider returned an invalid chat-completions response: {detail}",
        retryable=False,
    )


def _mapping(value: object, *, detail: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _invalid_response(detail)
    return value


def _raw_arguments(value: object) -> str | dict[str, Any] | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _parse_tool_arguments(
    value: object,
) -> tuple[dict[str, Any] | None, str | dict[str, Any] | None, str | None]:
    raw = _raw_arguments(value)
    if isinstance(value, Mapping):
        return dict(value), raw, None
    if not isinstance(value, str):
        detail = "arguments are missing" if value is None else "arguments are not JSON"
        return None, raw, detail
    try:
        parsed: object = json.loads(value)
    except json.JSONDecodeError as error:
        return None, raw, f"invalid JSON at character {error.pos}"
    if not isinstance(parsed, Mapping):
        return None, raw, "arguments must decode to a JSON object"
    return dict(parsed), raw, None


def _normalize_tool_call(value: object, *, index: int) -> ToolCall:
    call = _mapping(value, detail=f"tool call {index} is not an object")
    identifier = call.get("id")
    call_id = identifier if isinstance(identifier, str) else ""
    function_value = call.get("function")
    if not isinstance(function_value, Mapping):
        return ToolCall(
            id=call_id,
            name="",
            arguments=None,
            parse_error="tool function payload is missing",
        )
    name_value = function_value.get("name")
    name = name_value if isinstance(name_value, str) else ""
    arguments, raw_arguments, parse_error = _parse_tool_arguments(
        function_value.get("arguments")
    )
    return ToolCall(
        id=call_id,
        name=name,
        arguments=arguments,
        raw_arguments=raw_arguments,
        parse_error=parse_error,
    )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _normalize_usage(value: object) -> Usage | None:
    if not isinstance(value, Mapping):
        return None
    return Usage(
        input_tokens=_optional_int(value.get("prompt_tokens")),
        output_tokens=_optional_int(value.get("completion_tokens")),
        total_tokens=_optional_int(value.get("total_tokens")),
        cost=_optional_float(value.get("cost")),
    )


def _native_structured_output(
    message: Mapping[str, object],
    *,
    content: str | None,
    expected: bool,
) -> JsonObject | None:
    if not expected:
        return None
    for key in ("parsed", "structured_output"):
        value = message.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    if content is None:
        return None
    try:
        parsed: object = json.loads(content)
    except json.JSONDecodeError:
        return None
    return dict(parsed) if isinstance(parsed, Mapping) else None


def normalize_openai_response(
    payload: object,
    *,
    expect_structured_output: bool = False,
) -> ModelResponse:
    """Normalize one successful chat-completions response without SDK types."""
    root = _mapping(payload, detail="root is not an object")
    choices = root.get("choices")
    if not isinstance(choices, list) or not choices:
        raise _invalid_response("choices is missing or empty")
    choice = _mapping(choices[0], detail="first choice is not an object")
    message = _mapping(choice.get("message"), detail="choice message is not an object")

    content_value = message.get("content")
    if content_value is not None and not isinstance(content_value, str):
        raise _invalid_response("message content is not text or null")
    content = content_value if isinstance(content_value, str) else None

    calls_value = message.get("tool_calls", [])
    if calls_value is None:
        calls_value = []
    if not isinstance(calls_value, list):
        raise _invalid_response("message tool_calls is not a list")
    tool_calls = [
        _normalize_tool_call(value, index=index)
        for index, value in enumerate(calls_value)
    ]

    finish_value = choice.get("finish_reason")
    if finish_value is not None and not isinstance(finish_value, str):
        raise _invalid_response("finish_reason is not text or null")
    finish_reason = finish_value if isinstance(finish_value, str) else None
    return ModelResponse(
        content=content,
        tool_calls=tool_calls,
        structured_output=_native_structured_output(
            message,
            content=content,
            expected=expect_structured_output,
        ),
        finish_reason=finish_reason,
        usage=_normalize_usage(root.get("usage")),
        raw=payload,
    )


class OpenAICompatibleProvider:
    """Pooled asynchronous client for an OpenAI-compatible endpoint."""

    __slots__ = ("_client", "_closed")

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        api_key_header: str = "Authorization",
        api_key_prefix: str = "Bearer ",
        alternate_auth_headers: tuple[str, ...] = (),
    ) -> None:
        if not isinstance(config, OpenAICompatibleProviderConfig):
            raise TypeError("config must be an OpenAICompatibleProviderConfig")
        base_url = f"{config.base_url.rstrip('/')}/"
        headers = httpx.Headers(
            {name: _secret_value(value) for name, value in config.headers.items()}
        )
        auth_headers = (api_key_header, *alternate_auth_headers)
        if config.api_key is not None and not any(
            header in headers for header in auth_headers
        ):
            headers[api_key_header] = (
                f"{api_key_prefix}{config.api_key.get_secret_value()}"
            )
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=float(config.timeout_seconds),
            transport=transport,
        )
        self._closed = False

    def __repr__(self) -> str:
        return f"{type(self).__name__}(closed={self._closed!r})"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    @property
    def closed(self) -> bool:
        return self._closed

    def _request_path(self, request: ModelRequest) -> str:
        return "chat/completions"

    def _request_params(self, request: ModelRequest) -> dict[str, str] | None:
        return None

    def _request_payload(self, request: ModelRequest) -> JsonObject:
        return build_openai_request(request)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if self._closed:
            raise ProviderRequestError("Provider client is closed", retryable=False)
        try:
            response = await self._client.post(
                self._request_path(request),
                params=self._request_params(request),
                json=self._request_payload(request),
            )
        except httpx.TimeoutException as error:
            raise TimeoutError("Provider request timed out") from error
        except httpx.NetworkError as error:
            raise ProviderRequestError(
                f"Provider transport failed with {type(error).__name__}",
                retryable=True,
            ) from error
        except httpx.RequestError as error:
            raise ProviderRequestError(
                f"Provider transport failed with {type(error).__name__}",
                retryable=False,
            ) from error

        if not response.is_success:
            raise ProviderRequestError(
                f"Provider returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            payload: object = response.json()
        except ValueError as error:
            raise _invalid_response("body is not valid JSON") from error
        return normalize_openai_response(
            payload,
            expect_structured_output=request.output_schema is not None,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._client.aclose()


__all__ = [
    "OpenAICompatibleProvider",
    "build_openai_request",
    "normalize_openai_response",
]
