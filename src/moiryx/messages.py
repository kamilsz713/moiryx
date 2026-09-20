"""Provider-agnostic message models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias

JsonObject: TypeAlias = dict[str, Any]
RawArguments: TypeAlias = str | JsonObject | None


@dataclass(slots=True)
class ToolCall:
    """A normalized tool call, including recoverable malformed arguments."""

    id: str
    name: str
    arguments: JsonObject | None
    raw_arguments: RawArguments = None
    parse_error: str | None = None


@dataclass(slots=True)
class SystemMessage:
    """System instructions sent at the start of a run."""

    content: str


@dataclass(slots=True)
class UserMessage:
    """A user prompt or protocol-level corrective instruction."""

    content: str


@dataclass(slots=True)
class AssistantMessage:
    """An assistant response retained in normalized history."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(slots=True)
class ToolMessage:
    """A tool result; status stays local and is not sent to providers."""

    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


@dataclass(slots=True)
class RepairMessage:
    """An internal correction that is not a new user prompt."""

    content: str


Message: TypeAlias = (
    SystemMessage | UserMessage | AssistantMessage | ToolMessage | RepairMessage
)

__all__ = [
    "AssistantMessage",
    "Message",
    "RawArguments",
    "RepairMessage",
    "SystemMessage",
    "ToolCall",
    "ToolMessage",
    "UserMessage",
]
