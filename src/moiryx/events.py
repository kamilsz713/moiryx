"""Typed, provider-neutral runtime events and ambient event sinks."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Protocol, TypeAlias

from pydantic import BaseModel

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
EventResult: TypeAlias = str | BaseModel | Mapping[str, Any] | None


def _timestamp() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    """Base class for every event exposed by the Moiryx runtime."""

    run_id: str | None = None
    parent_run_id: str | None = None
    timestamp: datetime = field(default_factory=_timestamp)

    @property
    def kind(self) -> str:
        """Stable wire name used by persistence and non-Python consumers."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True, kw_only=True)
class Status(Event):
    message: str

    @property
    def kind(self) -> str:
        return "status"


@dataclass(frozen=True, slots=True, kw_only=True)
class TextDelta(Event):
    text: str
    channel: str = "assistant"

    @property
    def kind(self) -> str:
        return "text.delta"


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentStarted(Event):
    name: str
    model_alias: str
    model_id: str
    provider: str

    @property
    def kind(self) -> str:
        return "agent.started"


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentFinished(Event):
    name: str
    status: Literal["completed", "failed", "cancelled"]
    duration_ms: float
    result: EventResult = None
    error_type: str | None = None

    @property
    def kind(self) -> str:
        return "agent.finished"


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolStarted(Event):
    tool_call_id: str
    tool: str
    arguments: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))

    @property
    def kind(self) -> str:
        return "tool.started"


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolFinished(Event):
    tool_call_id: str
    tool: str
    output: str
    is_error: bool
    duration_ms: float

    @property
    def kind(self) -> str:
        return "tool.finished"


@dataclass(frozen=True, slots=True, kw_only=True)
class Artifact(Event):
    path: str
    title: str | None = None
    media_type: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def kind(self) -> str:
        return "artifact"


@dataclass(frozen=True, slots=True, kw_only=True)
class UsageEvent(Event):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None

    @property
    def kind(self) -> str:
        return "usage"


@dataclass(frozen=True, slots=True, kw_only=True)
class Warning(Event):
    message: str
    code: str | None = None

    @property
    def kind(self) -> str:
        return "warning"


@dataclass(frozen=True, slots=True, kw_only=True)
class Final(Event):
    """Top-level application result; agent runs use :class:`AgentFinished`."""

    content: str
    format: Literal["markdown", "plain", "json"] = "markdown"
    data: JsonValue = None

    @property
    def kind(self) -> str:
        return "final"


RuntimeEvent: TypeAlias = (
    Status
    | TextDelta
    | AgentStarted
    | AgentFinished
    | ToolStarted
    | ToolFinished
    | Artifact
    | UsageEvent
    | Warning
    | Final
)


class EventSink(Protocol):
    """A callable accepting events, synchronously or asynchronously."""

    def __call__(self, event: RuntimeEvent) -> Awaitable[None] | None: ...


_EVENT_SINK: ContextVar[EventSink | None] = ContextVar(
    "moiryx_event_sink", default=None
)
_RUN_ID: ContextVar[str | None] = ContextVar("moiryx_run_id", default=None)


@contextmanager
def event_sink(sink: EventSink | None) -> Iterator[None]:
    """Bind an event sink for agent calls made in the current async context."""
    token = _EVENT_SINK.set(sink)
    try:
        yield
    finally:
        _EVENT_SINK.reset(token)


@contextmanager
def run_scope(run_id: str) -> Iterator[None]:
    """Bind a run ID so nested agents can identify their parent run."""
    token = _RUN_ID.set(run_id)
    try:
        yield
    finally:
        _RUN_ID.reset(token)


def current_run_id() -> str | None:
    """Return the nearest active agent run ID, if any."""
    return _RUN_ID.get()


async def emit_event(event: RuntimeEvent) -> None:
    """Deliver one event to the ambient sink, preserving backpressure."""
    sink = _EVENT_SINK.get()
    if sink is None:
        return
    result = sink(event)
    if inspect.isawaitable(result):
        await result


def _jsonable(value: Any) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return {"type": type(value).__name__}


def event_to_dict(event: RuntimeEvent) -> dict[str, JsonValue]:
    """Convert an event to its versioned JSON-compatible wire form."""
    values = {item.name: getattr(event, item.name) for item in fields(event)}
    return {
        "schema_version": 1,
        "kind": event.kind,
        **{key: _jsonable(value) for key, value in values.items()},
    }


@contextmanager
def collect_events() -> Iterator[list[RuntimeEvent]]:
    """Collect ambient events; primarily useful in tests and small adapters."""
    events: list[RuntimeEvent] = []

    def append(event: RuntimeEvent) -> None:
        events.append(event)

    with event_sink(append):
        yield events


__all__ = [
    "AgentFinished",
    "AgentStarted",
    "Artifact",
    "Event",
    "EventSink",
    "Final",
    "JsonValue",
    "RuntimeEvent",
    "Status",
    "TextDelta",
    "ToolFinished",
    "ToolStarted",
    "UsageEvent",
    "Warning",
    "collect_events",
    "current_run_id",
    "emit_event",
    "event_sink",
    "event_to_dict",
    "run_scope",
]
