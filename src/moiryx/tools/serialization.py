"""Normalization and bounded serialization of custom tool results."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from pydantic import BaseModel, TypeAdapter

from moiryx.errors import ToolExecutionError
from moiryx.messages import ToolMessage


def serialize_tool_result(
    result: object,
    *,
    return_adapter: TypeAdapter[Any] | None = None,
    max_chars: int = 50_000,
) -> str:
    """Serialize a supported result and visibly truncate oversized content."""
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars <= 0:
        raise ValueError("max_chars must be a positive integer")

    try:
        normalized = (
            return_adapter.dump_python(result, mode="json", warnings="error")
            if return_adapter is not None
            else _normalize_without_adapter(result)
        )
        content = (
            normalized
            if isinstance(normalized, str)
            else json.dumps(
                normalized,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        )
    except (TypeError, ValueError) as error:
        raise ToolExecutionError(
            f"Tool result could not be serialized ({type(error).__name__})"
        ) from error

    if len(content) <= max_chars:
        return content
    marker = f"...[TRUNCATED BY MOIRYX: original output exceeded {max_chars} chars]"
    return content[:max_chars] + marker


def _normalize_without_adapter(result: object) -> object:
    if isinstance(result, str) or result is None:
        return result
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if is_dataclass(result) and not isinstance(result, type):
        return asdict(result)
    if isinstance(result, (bool, int, float, list, dict)):
        return result
    raise TypeError(f"Unsupported tool result type: {type(result).__name__}")


def build_tool_message(
    tool_call_id: str,
    name: str,
    result: object,
    *,
    return_adapter: TypeAdapter[Any] | None = None,
    max_chars: int = 50_000,
) -> ToolMessage:
    """Create a provider-neutral textual message from one tool result."""
    try:
        content = serialize_tool_result(
            result,
            return_adapter=return_adapter,
            max_chars=max_chars,
        )
    except ToolExecutionError as error:
        raise ToolExecutionError(error.message, tool_name=name) from error
    return ToolMessage(
        tool_call_id=tool_call_id,
        name=name,
        content=content,
    )


__all__ = ["build_tool_message", "serialize_tool_result"]
