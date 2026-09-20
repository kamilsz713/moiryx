"""Provider-neutral runtime loops for prepared agents."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, TypeAlias, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from moiryx.agent_spec import AgentSpec
from moiryx.config import RuntimeConfig
from moiryx.errors import (
    AgentProtocolError,
    MaxStepsExceeded,
    ProviderCapabilityError,
    ToolCallRepairError,
)
from moiryx.messages import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from moiryx.model_registry import ResolvedModel
from moiryx.models import (
    GenerationOptions,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ToolDefinition,
)
from moiryx.observability import RunObserver
from moiryx.output import StructuredOutputRepairTracker, build_final_tool
from moiryx.providers import ProviderAdapter
from moiryx.retry import ProviderRetry
from moiryx.tools import (
    FINAL_TOOL_NAME,
    ToolExecutor,
    ToolRepairTracker,
    execute_prepared_batch,
    preflight_tool_calls,
)

StructuredOutputMode: TypeAlias = Literal["synthetic_tool", "native_schema"]
_ResultT = TypeVar("_ResultT")

_SYNTHETIC_PROTOCOL_SUFFIX = (
    "When the task is complete, return the final answer by calling "
    f"{FINAL_TOOL_NAME} exactly once with arguments matching the required schema. "
    "Do not return the final structured answer as plain text."
)
_NATIVE_PROTOCOL_SUFFIX = (
    "Return the final answer through the provider's required native structured "
    "output schema. Do not return the final structured answer as plain text."
)


@dataclass(slots=True)
class RunContext:
    """Mutable state owned exclusively by one invocation of an agent."""

    run_id: str
    messages: list[Message]
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    step: int = 0


def _run_fields(spec: AgentSpec, model: ResolvedModel) -> dict[str, object]:
    return {
        "agent": spec.name,
        "model_alias": model.alias,
        "provider": model.provider,
        "model_id": model.model,
    }


async def _observe_run(
    operation: Callable[[], Awaitable[_ResultT]],
    *,
    context: RunContext,
    observer: RunObserver,
    spec: AgentSpec,
    model: ResolvedModel,
    result_type: str,
) -> _ResultT:
    fields = _run_fields(spec, model)
    observer.emit(
        "run_started",
        run_id=context.run_id,
        level=logging.INFO,
        started_at=context.started_at,
        **fields,
    )
    try:
        result = await operation()
    except BaseException as error:
        context.ended_at = datetime.now(UTC)
        observer.emit(
            "run_failed",
            run_id=context.run_id,
            level=logging.ERROR,
            ended_at=context.ended_at,
            duration_ms=(context.ended_at - context.started_at).total_seconds() * 1000,
            steps=context.step,
            error_type=type(error).__name__,
            **fields,
        )
        raise
    context.ended_at = datetime.now(UTC)
    observer.emit(
        "run_completed",
        run_id=context.run_id,
        level=logging.INFO,
        ended_at=context.ended_at,
        duration_ms=(context.ended_at - context.started_at).total_seconds() * 1000,
        steps=context.step,
        result_type=result_type,
        **fields,
    )
    return result


def _emit_model_requested(
    observer: RunObserver,
    context: RunContext,
    *,
    tool_count: int,
    structured: bool,
) -> None:
    observer.emit(
        "model_requested",
        run_id=context.run_id,
        level=logging.DEBUG,
        step=context.step,
        tool_count=tool_count,
        structured=structured,
    )


def _emit_model_responded(
    observer: RunObserver,
    context: RunContext,
    response: ModelResponse,
) -> None:
    fields: dict[str, object] = {
        "step": context.step,
        "finish_reason": response.finish_reason,
        "tool_call_count": len(response.tool_calls),
    }
    if response.usage is not None:
        fields["usage"] = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.total_tokens,
            "cost": response.usage.cost,
        }
    if observer.include_raw_response:
        fields["raw_response"] = response.raw
    observer.emit(
        "model_responded",
        run_id=context.run_id,
        level=logging.DEBUG,
        **fields,
    )


def _emit_provider_retry(
    observer: RunObserver,
    context: RunContext,
    attempt: int,
    delay: float,
    error: Exception,
) -> None:
    observer.emit(
        "provider_retry",
        run_id=context.run_id,
        level=logging.WARNING,
        step=context.step,
        attempt=attempt,
        delay_seconds=delay,
        error_type=type(error).__name__,
    )


def _emit_tool_requests(
    observer: RunObserver,
    context: RunContext,
    response: ModelResponse,
) -> None:
    for call in response.tool_calls:
        observer.emit(
            "tool_requested",
            run_id=context.run_id,
            level=logging.DEBUG,
            step=context.step,
            tool_call_id=call.id,
            tool=call.name,
        )


def _emit_tool_results(
    observer: RunObserver,
    context: RunContext,
    messages: Sequence[ToolMessage],
) -> None:
    for message in messages:
        failed = message.is_error
        observer.emit(
            "tool_failed" if failed else "tool_completed",
            run_id=context.run_id,
            level=logging.WARNING if failed else logging.DEBUG,
            step=context.step,
            tool_call_id=message.tool_call_id,
            tool=message.name,
        )


def _emit_repair(
    observer: RunObserver,
    context: RunContext,
    event: str,
    *,
    calls: int,
) -> None:
    observer.emit(
        event,
        run_id=context.run_id,
        level=logging.WARNING,
        step=context.step,
        call_count=calls,
    )


async def _execute_text_agent(
    *,
    provider: ProviderAdapter,
    spec: AgentSpec,
    model: ResolvedModel,
    tools: Sequence[ToolDefinition],
    generation: GenerationOptions,
    runtime: RuntimeConfig,
    context: RunContext,
    observer: RunObserver,
    provider_retry: ProviderRetry | None = None,
) -> str:
    """Execute an already observed text-agent run."""
    executor = ToolExecutor(runtime.tool_timeout_seconds)
    retry = provider_retry or ProviderRetry(runtime.provider_retry_attempts)
    repair_tracker = ToolRepairTracker(
        runtime.tool_call_repair_attempts,
        agent_name=spec.name,
        model_alias=model.alias,
        provider_name=model.provider,
        model_id=model.model,
        run_id=context.run_id,
    )
    tool_schemas = [definition.schema for definition in tools]
    repair_pending = False

    for step in range(1, spec.max_steps + 1):
        context.step = step
        _emit_model_requested(
            observer,
            context,
            tool_count=len(tool_schemas),
            structured=False,
        )
        response = await retry.complete(
            provider,
            ModelRequest(
                model=model.model,
                messages=list(context.messages),
                tools=list(tool_schemas),
                generation=generation,
            ),
            agent_name=spec.name,
            model_alias=model.alias,
            provider_name=model.provider,
            model_id=model.model,
            run_id=context.run_id,
            on_retry=lambda attempt, delay, error: _emit_provider_retry(
                observer,
                context,
                attempt,
                delay,
                error,
            ),
        )
        _emit_model_responded(observer, context, response)
        _emit_tool_requests(observer, context, response)

        if response.tool_calls:
            context.messages.append(
                AssistantMessage(
                    content=response.content,
                    tool_calls=list(response.tool_calls),
                )
            )
            preflight = preflight_tool_calls(response.tool_calls, tools)
            if not preflight.is_valid:
                _emit_repair(
                    observer,
                    context,
                    "tool_call_repair_started",
                    calls=len(response.tool_calls),
                )
                try:
                    feedback = repair_tracker.feedback_for(preflight)
                except ToolCallRepairError:
                    _emit_repair(
                        observer,
                        context,
                        "tool_call_repair_failed",
                        calls=len(response.tool_calls),
                    )
                    raise
                context.messages.extend(feedback)
                repair_pending = True
                continue
            if repair_pending:
                _emit_repair(
                    observer,
                    context,
                    "tool_call_repaired",
                    calls=len(response.tool_calls),
                )
                repair_pending = False

            tool_messages = await execute_prepared_batch(
                preflight,
                executor,
                max_output_chars=runtime.max_tool_output_chars,
            )
            context.messages.extend(tool_messages)
            _emit_tool_results(observer, context, tool_messages)
            continue

        if response.content is None:
            raise AgentProtocolError(
                "Provider response has neither content nor tool calls",
                agent_name=spec.name,
                model_alias=model.alias,
                provider_name=model.provider,
                model_id=model.model,
                run_id=context.run_id,
            )
        if repair_pending:
            _emit_repair(
                observer,
                context,
                "tool_call_repaired",
                calls=0,
            )
        return response.content

    raise MaxStepsExceeded(
        "Agent exceeded its maximum number of model steps",
        agent_name=spec.name,
        model_alias=model.alias,
        provider_name=model.provider,
        model_id=model.model,
        run_id=context.run_id,
        limit=spec.max_steps,
    )


async def execute_text_agent(
    *,
    provider: ProviderAdapter,
    spec: AgentSpec,
    model: ResolvedModel,
    tools: Sequence[ToolDefinition],
    generation: GenerationOptions,
    runtime: RuntimeConfig,
    prompt: str,
    provider_retry: ProviderRetry | None = None,
    observer: RunObserver | None = None,
) -> str:
    """Execute a text agent until final content or a concrete terminal error."""
    if spec.output_model is not None:
        raise ValueError("text runtime cannot execute a structured agent")
    context = RunContext(
        run_id=uuid4().hex,
        messages=[SystemMessage(spec.instructions), UserMessage(prompt)],
    )
    active_observer = observer or RunObserver()
    return await _observe_run(
        lambda: _execute_text_agent(
            provider=provider,
            spec=spec,
            model=model,
            tools=tools,
            generation=generation,
            runtime=runtime,
            context=context,
            observer=active_observer,
            provider_retry=provider_retry,
        ),
        context=context,
        observer=active_observer,
        spec=spec,
        model=model,
        result_type="text",
    )


def _select_structured_output_mode(
    *,
    capabilities: ProviderCapabilities,
    has_user_tools: bool,
    spec: AgentSpec,
    model: ResolvedModel,
) -> StructuredOutputMode:
    if capabilities.tool_calling:
        return "synthetic_tool"
    if capabilities.native_structured_output and not has_user_tools:
        return "native_schema"
    raise ProviderCapabilityError(
        "Structured output requires tool calling or guaranteed native "
        "structured output without user tools",
        agent_name=spec.name,
        model_alias=model.alias,
        provider_name=model.provider,
        model_id=model.model,
    )


def _structured_validation_feedback(error: ValidationError) -> str:
    issues: list[str] = []
    for item in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = ".".join(str(part) for part in item["loc"]) or "result"
        issues.append(f"- {location}: {item['msg']}")
    return (
        "Native structured output did not match the required schema. Correct the "
        "result and try again.\nValidation errors:\n" + "\n".join(issues)
    )


async def _execute_structured_agent(
    *,
    provider: ProviderAdapter,
    spec: AgentSpec,
    model: ResolvedModel,
    tools: Sequence[ToolDefinition],
    capabilities: ProviderCapabilities,
    generation: GenerationOptions,
    runtime: RuntimeConfig,
    output_model: type[BaseModel],
    mode: StructuredOutputMode,
    context: RunContext,
    observer: RunObserver,
    provider_retry: ProviderRetry | None = None,
) -> BaseModel:
    """Execute an already observed structured-agent run."""
    retry = provider_retry or ProviderRetry(runtime.provider_retry_attempts)
    executor = ToolExecutor(runtime.tool_timeout_seconds)
    tool_repair_tracker = ToolRepairTracker(
        runtime.tool_call_repair_attempts,
        agent_name=spec.name,
        model_alias=model.alias,
        provider_name=model.provider,
        model_id=model.model,
        run_id=context.run_id,
    )
    structured_repair_tracker = StructuredOutputRepairTracker(
        runtime.structured_output_retries,
        agent_name=spec.name,
        model_alias=model.alias,
        provider_name=model.provider,
        model_id=model.model,
        run_id=context.run_id,
    )
    final_tool = build_final_tool(output_model)
    request_tools = (
        [definition.schema for definition in (*tools, final_tool)]
        if mode == "synthetic_tool"
        else []
    )
    output_schema = (
        output_model.model_json_schema() if mode == "native_schema" else None
    )
    repair_pending = False

    for step in range(1, spec.max_steps + 1):
        context.step = step
        _emit_model_requested(
            observer,
            context,
            tool_count=len(request_tools),
            structured=True,
        )
        response = await retry.complete(
            provider,
            ModelRequest(
                model=model.model,
                messages=list(context.messages),
                tools=list(request_tools),
                output_schema=output_schema,
                generation=generation,
            ),
            agent_name=spec.name,
            model_alias=model.alias,
            provider_name=model.provider,
            model_id=model.model,
            run_id=context.run_id,
            on_retry=lambda attempt, delay, error: _emit_provider_retry(
                observer,
                context,
                attempt,
                delay,
                error,
            ),
        )
        _emit_model_responded(observer, context, response)
        _emit_tool_requests(observer, context, response)
        context.messages.append(
            AssistantMessage(
                content=response.content,
                tool_calls=list(response.tool_calls),
            )
        )

        if mode == "native_schema":
            if response.tool_calls:
                context.messages.append(
                    structured_repair_tracker.feedback_for(
                        "Native structured output must not contain tool calls. "
                        "Return one result matching the required schema."
                    )
                )
                continue
            if response.structured_output is None:
                context.messages.append(
                    structured_repair_tracker.feedback_for(
                        "Return the final result through native structured output. "
                        "Plain text, Markdown, and embedded JSON are not accepted."
                    )
                )
                continue
            try:
                result = output_model.model_validate(response.structured_output)
            except ValidationError as error:
                context.messages.append(
                    structured_repair_tracker.feedback_for(
                        _structured_validation_feedback(error)
                    )
                )
                continue
            observer.emit(
                "structured_output_validated",
                run_id=context.run_id,
                level=logging.DEBUG,
                step=context.step,
                mode=mode,
            )
            return result

        final_calls = [
            call for call in response.tool_calls if call.name.strip() == FINAL_TOOL_NAME
        ]
        if len(final_calls) > 1:
            context.messages.append(
                structured_repair_tracker.feedback_for(
                    f"Call {FINAL_TOOL_NAME} exactly once and without any other "
                    "tool calls."
                )
            )
            continue
        if final_calls and len(response.tool_calls) > 1:
            context.messages.append(
                structured_repair_tracker.feedback_for(
                    f"Call {FINAL_TOOL_NAME} alone, after all normal tool calls "
                    "are complete. No tool from this response was executed."
                )
            )
            continue
        if final_calls:
            final_call = final_calls[0]
            preflight = preflight_tool_calls([final_call], [final_tool])
            if preflight.is_valid:
                observer.emit(
                    "structured_output_validated",
                    run_id=context.run_id,
                    level=logging.DEBUG,
                    step=context.step,
                    mode=mode,
                )
                return preflight.calls[0].arguments
            issue = preflight.issues[0]
            context.messages.append(
                structured_repair_tracker.feedback_for(
                    "Final structured output is invalid. " + issue.feedback,
                    tool_call_id=issue.call_id,
                )
            )
            continue

        if response.tool_calls:
            preflight = preflight_tool_calls(response.tool_calls, tools)
            if not preflight.is_valid:
                _emit_repair(
                    observer,
                    context,
                    "tool_call_repair_started",
                    calls=len(response.tool_calls),
                )
                try:
                    feedback = tool_repair_tracker.feedback_for(preflight)
                except ToolCallRepairError:
                    _emit_repair(
                        observer,
                        context,
                        "tool_call_repair_failed",
                        calls=len(response.tool_calls),
                    )
                    raise
                context.messages.extend(feedback)
                repair_pending = True
                continue
            if repair_pending:
                _emit_repair(
                    observer,
                    context,
                    "tool_call_repaired",
                    calls=len(response.tool_calls),
                )
                repair_pending = False
            tool_messages = await execute_prepared_batch(
                preflight,
                executor,
                max_output_chars=runtime.max_tool_output_chars,
            )
            context.messages.extend(tool_messages)
            _emit_tool_results(observer, context, tool_messages)
            continue

        context.messages.append(
            structured_repair_tracker.feedback_for(
                f"Return the final result by calling {FINAL_TOOL_NAME} exactly "
                "once. Plain text, Markdown, and embedded JSON are not accepted."
            )
        )

    raise MaxStepsExceeded(
        "Agent exceeded its maximum number of model steps",
        agent_name=spec.name,
        model_alias=model.alias,
        provider_name=model.provider,
        model_id=model.model,
        run_id=context.run_id,
        limit=spec.max_steps,
    )


async def execute_structured_agent(
    *,
    provider: ProviderAdapter,
    spec: AgentSpec,
    model: ResolvedModel,
    tools: Sequence[ToolDefinition],
    capabilities: ProviderCapabilities,
    generation: GenerationOptions,
    runtime: RuntimeConfig,
    prompt: str,
    provider_retry: ProviderRetry | None = None,
    observer: RunObserver | None = None,
) -> BaseModel:
    """Execute a structured agent through a final tool or native schema path."""
    output_model = spec.output_model
    if output_model is None:
        raise ValueError("structured runtime requires an output model")
    mode = _select_structured_output_mode(
        capabilities=capabilities,
        has_user_tools=bool(tools) or bool(spec.tool_names),
        spec=spec,
        model=model,
    )
    protocol_suffix = (
        _SYNTHETIC_PROTOCOL_SUFFIX
        if mode == "synthetic_tool"
        else _NATIVE_PROTOCOL_SUFFIX
    )
    context = RunContext(
        run_id=uuid4().hex,
        messages=[
            SystemMessage(f"{spec.instructions}\n\n{protocol_suffix}"),
            UserMessage(prompt),
        ],
    )
    active_observer = observer or RunObserver()
    return await _observe_run(
        lambda: _execute_structured_agent(
            provider=provider,
            spec=spec,
            model=model,
            tools=tools,
            capabilities=capabilities,
            generation=generation,
            runtime=runtime,
            output_model=output_model,
            mode=mode,
            context=context,
            observer=active_observer,
            provider_retry=provider_retry,
        ),
        context=context,
        observer=active_observer,
        spec=spec,
        model=model,
        result_type="structured",
    )


__all__ = ["RunContext", "execute_structured_agent", "execute_text_agent"]
