"""Whole-batch validation and conservative repair of tool calls."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Literal

from pydantic import BaseModel, ValidationError

from moiryx.errors import ToolCallRepairError, ToolExecutionError, ToolTimeoutError
from moiryx.messages import RawArguments, RepairMessage, ToolCall, ToolMessage
from moiryx.models import ToolDefinition
from moiryx.tools.executor import ToolExecutor
from moiryx.tools.serialization import build_tool_message

IssueKind = Literal["unknown_tool", "parse", "validation"]
RepairFeedback = ToolMessage | RepairMessage


@dataclass(frozen=True, slots=True)
class PreparedToolCall:
    """One exact tool call with arguments validated during batch preflight."""

    id: str
    name: str
    definition: ToolDefinition
    arguments: BaseModel
    raw_arguments: RawArguments


@dataclass(frozen=True, slots=True)
class ToolCallIssue:
    """A concise, model-facing problem found without executing a tool."""

    call_id: str
    name: str
    kind: IssueKind
    summary: str
    feedback: str
    raw_arguments: RawArguments
    parse_error: str | None
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ToolBatchPreflight:
    """Atomic preflight result: prepared calls or issues, never both."""

    calls: tuple[PreparedToolCall, ...]
    issues: tuple[ToolCallIssue, ...]

    def __post_init__(self) -> None:
        if self.calls and self.issues:
            raise ValueError("preflight result cannot contain calls and issues")

    @property
    def is_valid(self) -> bool:
        return not self.issues

    @property
    def fingerprint(self) -> tuple[str, ...]:
        return tuple(issue.fingerprint for issue in self.issues)


def preflight_tool_calls(
    calls: Sequence[ToolCall],
    tools: Iterable[ToolDefinition],
) -> ToolBatchPreflight:
    """Resolve, repair, and validate every call before allowing any execution."""
    definitions = {definition.name: definition for definition in tools}
    available = tuple(definitions)
    prepared: list[PreparedToolCall] = []
    issues: list[ToolCallIssue] = []

    for call in calls:
        name = call.name.strip()
        definition = definitions.get(name)
        raw_arguments = (
            call.raw_arguments if call.raw_arguments is not None else call.arguments
        )
        if definition is None:
            issues.append(
                _unknown_tool_issue(
                    call,
                    normalized_name=name,
                    available=available,
                    raw_arguments=raw_arguments,
                )
            )
            continue

        parsed, parse_error = _parse_arguments(call)
        if parsed is None:
            issues.append(
                _parse_issue(
                    call,
                    normalized_name=name,
                    raw_arguments=raw_arguments,
                    parse_error=parse_error or "arguments are not a JSON object",
                )
            )
            continue

        try:
            validated = _validate_with_wrapper_repair(definition, parsed)
        except ValidationError as error:
            issues.append(
                _validation_issue(
                    call,
                    normalized_name=name,
                    definition=definition,
                    raw_arguments=raw_arguments,
                    error=error,
                )
            )
            continue

        prepared.append(
            PreparedToolCall(
                id=call.id,
                name=name,
                definition=definition,
                arguments=validated,
                raw_arguments=raw_arguments,
            )
        )

    if issues:
        prepared.clear()
    return ToolBatchPreflight(calls=tuple(prepared), issues=tuple(issues))


def _parse_arguments(call: ToolCall) -> tuple[dict[str, object] | None, str | None]:
    if call.arguments is not None:
        return dict(call.arguments), None
    raw = call.raw_arguments
    if isinstance(raw, dict):
        return dict(raw), None
    if not isinstance(raw, str):
        return None, call.parse_error or "arguments are missing"

    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError as error:
        detail = call.parse_error or f"invalid JSON at character {error.pos}"
        return None, detail
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError as error:
            detail = call.parse_error or f"invalid nested JSON at character {error.pos}"
            return None, detail
    if not isinstance(parsed, dict):
        return None, call.parse_error or "arguments must decode to a JSON object"
    return parsed, None


def _validate_with_wrapper_repair(
    definition: ToolDefinition,
    arguments: dict[str, object],
) -> BaseModel:
    try:
        return definition.input_model.model_validate(arguments)
    except ValidationError as original_error:
        can_unwrap = (
            set(arguments) == {"arguments"}
            and "arguments" not in definition.input_model.model_fields
            and isinstance(arguments["arguments"], dict)
        )
        if not can_unwrap:
            raise
        try:
            return definition.input_model.model_validate(arguments["arguments"])
        except ValidationError:
            raise original_error from None


def _canonical_raw(raw_arguments: RawArguments) -> str:
    if isinstance(raw_arguments, str):
        stripped = raw_arguments.strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        return json.dumps(
            parsed,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if isinstance(raw_arguments, dict):
        return json.dumps(
            raw_arguments,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=_fingerprint_default,
        )
    return "null"


def _fingerprint_default(value: object) -> str:
    value_type = type(value)
    return f"<non-json:{value_type.__module__}.{value_type.__qualname__}>"


def _fingerprint(
    *,
    name: str,
    raw_arguments: RawArguments,
    error_signature: str,
) -> str:
    value = "\x1f".join((name, _canonical_raw(raw_arguments), error_signature))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _call_label(call_id: str) -> str:
    return f" (call ID: {call_id})" if call_id.strip() else ""


def _unknown_tool_issue(
    call: ToolCall,
    *,
    normalized_name: str,
    available: tuple[str, ...],
    raw_arguments: RawArguments,
) -> ToolCallIssue:
    suggestion = get_close_matches(normalized_name, available, n=1, cutoff=0.6)
    available_text = ", ".join(available) if available else "none"
    suggestion_text = f" Did you mean '{suggestion[0]}'?" if suggestion else ""
    summary = f"Unknown tool '{normalized_name or call.name}'."
    feedback = (
        f"{summary}{_call_label(call.id)} Available tools: {available_text}."
        f"{suggestion_text} Submit a corrected tool call."
    )
    return ToolCallIssue(
        call_id=call.id,
        name=normalized_name,
        kind="unknown_tool",
        summary=summary,
        feedback=feedback,
        raw_arguments=raw_arguments,
        parse_error=call.parse_error,
        fingerprint=_fingerprint(
            name=normalized_name,
            raw_arguments=raw_arguments,
            error_signature="unknown_tool",
        ),
    )


def _parse_issue(
    call: ToolCall,
    *,
    normalized_name: str,
    raw_arguments: RawArguments,
    parse_error: str,
) -> ToolCallIssue:
    headline = f"Tool arguments for '{normalized_name}' are not a valid JSON object"
    summary = f"{headline}: {parse_error}"
    feedback = (
        f"{headline}{_call_label(call.id)}. Correct the arguments and try again. "
        f"Parse error: {parse_error}."
    )
    return ToolCallIssue(
        call_id=call.id,
        name=normalized_name,
        kind="parse",
        summary=summary,
        feedback=feedback,
        raw_arguments=raw_arguments,
        parse_error=parse_error,
        fingerprint=_fingerprint(
            name=normalized_name,
            raw_arguments=raw_arguments,
            error_signature=f"parse:{parse_error}",
        ),
    )


def _validation_issue(
    call: ToolCall,
    *,
    normalized_name: str,
    definition: ToolDefinition,
    raw_arguments: RawArguments,
    error: ValidationError,
) -> ToolCallIssue:
    rendered_errors: list[str] = []
    signatures: list[str] = []
    for item in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = ".".join(str(part) for part in item["loc"]) or "arguments"
        rendered_errors.append(f"- {location}: {item['msg']}")
        signatures.append(f"{location}:{item['type']}")

    required = set(definition.input_model.model_json_schema().get("required", []))
    parameters = ", ".join(
        f"{name}{' (required)' if name in required else ''}"
        for name in definition.input_model.model_fields
    )
    headline = f"Tool call validation failed for '{normalized_name}'"
    first_error = rendered_errors[0].removeprefix("- ")
    summary = f"{headline}: {first_error}"
    error_text = "\n".join(rendered_errors)
    feedback = (
        f"{headline}{_call_label(call.id)}. Correct the tool call and try again.\n"
        f"Validation errors:\n{error_text}\n"
        f"Expected parameters: {parameters or 'none'}."
    )
    error_signature = "validation:" + "|".join(signatures)
    return ToolCallIssue(
        call_id=call.id,
        name=normalized_name,
        kind="validation",
        summary=summary,
        feedback=feedback,
        raw_arguments=raw_arguments,
        parse_error=call.parse_error,
        fingerprint=_fingerprint(
            name=normalized_name,
            raw_arguments=raw_arguments,
            error_signature=error_signature,
        ),
    )


def build_repair_feedback(
    result: ToolBatchPreflight,
) -> tuple[RepairFeedback, ...]:
    """Associate feedback with tool-call IDs whenever the protocol permits."""
    feedback: list[RepairFeedback] = []
    for issue in result.issues:
        if issue.call_id.strip():
            feedback.append(
                ToolMessage(
                    tool_call_id=issue.call_id,
                    name=issue.name,
                    content=issue.feedback,
                    is_error=True,
                )
            )
        else:
            feedback.append(RepairMessage(content=issue.feedback))
    return tuple(feedback)


class ToolRepairTracker:
    """Track repair rounds independently, including repeated fingerprints."""

    __slots__ = (
        "_agent_name",
        "_attempts",
        "_fingerprints",
        "_limit",
        "_model_alias",
        "_model_id",
        "_provider_name",
        "_run_id",
    )

    def __init__(
        self,
        limit: int,
        *,
        agent_name: str | None = None,
        model_alias: str | None = None,
        provider_name: str | None = None,
        model_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        self._limit = limit
        self._attempts = 0
        self._fingerprints: list[tuple[str, ...]] = []
        self._agent_name = agent_name
        self._model_alias = model_alias
        self._provider_name = provider_name
        self._model_id = model_id
        self._run_id = run_id

    @property
    def attempts(self) -> int:
        return self._attempts

    @property
    def fingerprints(self) -> tuple[tuple[str, ...], ...]:
        return tuple(self._fingerprints)

    def feedback_for(
        self,
        result: ToolBatchPreflight,
    ) -> tuple[RepairFeedback, ...]:
        """Consume one repair round or raise once no correction round remains."""
        if result.is_valid:
            raise ValueError("repair feedback requires an invalid preflight result")
        issue = result.issues[0]
        if self._attempts >= self._limit:
            raise ToolCallRepairError(
                "Tool call repair budget exhausted",
                raw_arguments=issue.raw_arguments,
                error_summary=issue.summary,
                agent_name=self._agent_name,
                model_alias=self._model_alias,
                provider_name=self._provider_name,
                model_id=self._model_id,
                run_id=self._run_id,
                tool_name=issue.name or None,
                attempts=self._attempts,
                limit=self._limit,
            )
        self._attempts += 1
        self._fingerprints.append(result.fingerprint)
        return build_repair_feedback(result)


async def execute_prepared_batch(
    result: ToolBatchPreflight,
    executor: ToolExecutor,
    *,
    max_output_chars: int = 50_000,
    on_start: Callable[[PreparedToolCall], Awaitable[None]] | None = None,
    on_finish: Callable[[PreparedToolCall, ToolMessage], Awaitable[None]] | None = None,
) -> tuple[ToolMessage, ...]:
    """Execute a successful preflight sequentially and serialize each result."""
    if not result.is_valid:
        raise ValueError("cannot execute a batch with preflight issues")
    messages: list[ToolMessage] = []
    for call in result.calls:
        if on_start is not None:
            await on_start(call)
        try:
            value = await executor.execute_validated(call.definition, call.arguments)
            message = build_tool_message(
                call.id,
                call.name,
                value,
                return_adapter=call.definition.return_adapter,
                max_chars=max_output_chars,
            )
        except (ToolExecutionError, ToolTimeoutError) as error:
            message = ToolMessage(
                tool_call_id=call.id,
                name=call.name,
                content=f"{type(error).__name__}: {error.message}",
                is_error=True,
            )
        if on_finish is not None:
            await on_finish(call, message)
        messages.append(message)
    return tuple(messages)


__all__ = [
    "PreparedToolCall",
    "RepairFeedback",
    "ToolBatchPreflight",
    "ToolCallIssue",
    "ToolRepairTracker",
    "build_repair_feedback",
    "execute_prepared_batch",
    "preflight_tool_calls",
]
