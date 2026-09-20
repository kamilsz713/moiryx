"""Tests for run logging, JSONL tracing, and central secret redaction."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from types import MappingProxyType

import pytest
from pydantic import BaseModel

from moiryx.agent_spec import AgentSpec
from moiryx.config import LoggingConfig, RuntimeConfig
from moiryx.errors import ProviderRequestError
from moiryx.messages import ToolCall
from moiryx.model_registry import ResolvedModel
from moiryx.models import GenerationOptions, ModelResponse, ToolDefinition
from moiryx.observability import LOGGER_NAME, RunObserver
from moiryx.providers import ScriptedFakeProvider
from moiryx.redaction import REDACTED, collect_secret_values, redact
from moiryx.retry import ProviderRetry
from moiryx.runtime import execute_structured_agent, execute_text_agent
from moiryx.tools import FINAL_TOOL_NAME
from moiryx.tools.definition import build_tool_definition


def _spec() -> AgentSpec:
    return AgentSpec(
        name="observer",
        model_alias="strong",
        instructions="Observe carefully.",
        tool_names=(),
        output_model=None,
        max_steps=4,
        generation=GenerationOptions(),
        source_path=Path("observer.md"),
    )


def _model() -> ResolvedModel:
    return ResolvedModel(
        alias="strong",
        provider="local",
        model="vendor/model",
        generation=GenerationOptions(),
        provider_options=MappingProxyType({}),
    )


async def _execute(
    provider: ScriptedFakeProvider,
    observer: RunObserver,
    *,
    tools: tuple[ToolDefinition, ...] = (),
    provider_retry: ProviderRetry | None = None,
) -> str:
    return await execute_text_agent(
        provider=provider,
        spec=_spec(),
        model=_model(),
        tools=tools,
        generation=GenerationOptions(),
        runtime=RuntimeConfig(provider_retry_attempts=0),
        prompt="Run it",
        observer=observer,
        provider_retry=provider_retry,
    )


def _read_runs(trace_dir: Path) -> dict[str, list[dict[str, object]]]:
    runs: dict[str, list[dict[str, object]]] = {}
    for trace_path in trace_dir.glob("*/events.jsonl"):
        lines = trace_path.read_text("utf-8").splitlines()
        runs[trace_path.parent.name] = [json.loads(line) for line in lines]
    return runs


@pytest.mark.asyncio
async def test_successful_run_emits_logging_and_isolated_jsonl_events(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def increment(value: int) -> int:
        return value + 1

    tool = build_tool_definition(increment)
    provider = ScriptedFakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("call-1", "increment", {"value": 1})]),
            ModelResponse(content="done"),
        ]
    )
    trace_dir = tmp_path / "traces"
    observer = RunObserver(LoggingConfig(level="DEBUG", trace_dir=trace_dir))
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)

    assert await _execute(provider, observer, tools=(tool,)) == "done"

    runs = _read_runs(trace_dir)
    assert len(runs) == 1
    run_id, events = next(iter(runs.items()))
    event_names = [event["event"] for event in events]
    assert event_names == [
        "run_started",
        "model_requested",
        "model_responded",
        "tool_requested",
        "tool_completed",
        "model_requested",
        "model_responded",
        "run_completed",
    ]
    assert all(event["run_id"] == run_id for event in events)
    assert all(str(event["timestamp"]).endswith("Z") for event in events)
    assert events[0]["agent"] == "observer"
    assert events[0]["model_alias"] == "strong"
    assert events[0]["provider"] == "local"
    assert events[-1]["steps"] == 2
    assert any('"event":"run_started"' in record.message for record in caplog.records)
    assert any('"event":"run_completed"' in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_failed_preflight_is_repaired_but_never_logged_as_executed(
    tmp_path: Path,
) -> None:
    def lookup(value: int) -> int:
        return value

    provider = ScriptedFakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("invalid", "lookup", {})]),
            ModelResponse(content="recovered"),
        ]
    )
    trace_dir = tmp_path / "traces"

    result = await _execute(
        provider,
        RunObserver(LoggingConfig(level="DEBUG", trace_dir=trace_dir)),
        tools=(build_tool_definition(lookup),),
    )

    assert result == "recovered"
    events = next(iter(_read_runs(trace_dir).values()))
    names = [event["event"] for event in events]
    assert "tool_call_repair_started" in names
    assert "tool_call_repaired" in names
    assert not any(
        event["event"] == "tool_completed" and event.get("tool_call_id") == "invalid"
        for event in events
    )


@pytest.mark.asyncio
async def test_tool_failure_has_warning_event_without_exception_details(
    tmp_path: Path,
) -> None:
    secret = "sentinel-tool-secret"

    def explode() -> None:
        raise RuntimeError(secret)

    provider = ScriptedFakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("broken", "explode", {})]),
            ModelResponse(content="continued"),
        ]
    )
    trace_dir = tmp_path / "traces"

    assert (
        await _execute(
            provider,
            RunObserver(
                LoggingConfig(level="DEBUG", trace_dir=trace_dir),
                secrets=(secret,),
            ),
            tools=(build_tool_definition(explode),),
        )
        == "continued"
    )

    serialized = next(trace_dir.glob("*/events.jsonl")).read_text("utf-8")
    events = next(iter(_read_runs(trace_dir).values()))
    failed = next(event for event in events if event["event"] == "tool_failed")
    assert failed["level"] == "WARNING"
    assert provider.requests[1].messages[-1].is_error is True
    assert secret not in serialized


@pytest.mark.asyncio
async def test_tool_result_text_does_not_determine_failure_status(
    tmp_path: Path,
) -> None:
    def describe() -> str:
        return "ToolExecutionError: this is just a log excerpt"

    provider = ScriptedFakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("quoted", "describe", {})]),
            ModelResponse(content="done"),
        ]
    )
    trace_dir = tmp_path / "traces"

    assert (
        await _execute(
            provider,
            RunObserver(LoggingConfig(level="DEBUG", trace_dir=trace_dir)),
            tools=(build_tool_definition(describe),),
        )
        == "done"
    )

    events = next(iter(_read_runs(trace_dir).values()))
    assert any(
        event["event"] == "tool_completed" and event["tool_call_id"] == "quoted"
        for event in events
    )
    assert not any(event["event"] == "tool_failed" for event in events)
    assert provider.requests[1].messages[-1].is_error is False


@pytest.mark.asyncio
async def test_concurrent_runs_never_mix_trace_files(tmp_path: Path) -> None:
    trace_dir = tmp_path / "traces"
    observer = RunObserver(LoggingConfig(level="DEBUG", trace_dir=trace_dir))

    results = await asyncio.gather(
        _execute(ScriptedFakeProvider([ModelResponse(content="first")]), observer),
        _execute(ScriptedFakeProvider([ModelResponse(content="second")]), observer),
    )

    assert results == ["first", "second"]
    runs = _read_runs(trace_dir)
    assert len(runs) == 2
    assert all(
        {event["run_id"] for event in events} == {run_id}
        for run_id, events in runs.items()
    )


@pytest.mark.asyncio
async def test_raw_response_requires_explicit_debug_and_is_redacted(
    tmp_path: Path,
) -> None:
    secret = "sentinel-provider-secret"
    plain_dir = tmp_path / "plain"
    debug_dir = tmp_path / "debug"
    raw = {
        "Authorization": f"Bearer {secret}",
        "nested": {"note": f"token={secret}"},
    }

    await _execute(
        ScriptedFakeProvider([ModelResponse(content="plain", raw=raw)]),
        RunObserver(
            LoggingConfig(level="DEBUG", trace_dir=plain_dir),
            secrets=(secret,),
        ),
    )
    await _execute(
        ScriptedFakeProvider([ModelResponse(content="debug", raw=raw)]),
        RunObserver(
            LoggingConfig(
                level="DEBUG",
                trace_dir=debug_dir,
                include_raw_response=True,
            ),
            secrets=(secret,),
        ),
    )

    plain = next(iter(_read_runs(plain_dir).values()))
    debug = next(iter(_read_runs(debug_dir).values()))
    plain_response = next(
        event for event in plain if event["event"] == "model_responded"
    )
    debug_response = next(
        event for event in debug if event["event"] == "model_responded"
    )
    assert "raw_response" not in plain_response
    assert debug_response["raw_response"] == {
        "Authorization": REDACTED,
        "nested": {"note": f"token={REDACTED}"},
    }
    assert secret not in next(debug_dir.glob("*/events.jsonl")).read_text("utf-8")


@pytest.mark.asyncio
async def test_failed_run_logs_only_redacted_error_metadata(tmp_path: Path) -> None:
    secret = "sentinel-request-secret"
    trace_dir = tmp_path / "traces"
    provider = ScriptedFakeProvider(
        [ProviderRequestError(f"failed with {secret}", retryable=False)]
    )

    with pytest.raises(ProviderRequestError):
        await _execute(
            provider,
            RunObserver(
                LoggingConfig(level="DEBUG", trace_dir=trace_dir),
                secrets=(secret,),
            ),
        )

    serialized = next(trace_dir.glob("*/events.jsonl")).read_text("utf-8")
    events = next(iter(_read_runs(trace_dir).values()))
    assert events[-1]["event"] == "run_failed"
    assert events[-1]["error_type"] == "ProviderRequestError"
    assert secret not in serialized


@pytest.mark.asyncio
async def test_provider_retry_uses_warning_level(tmp_path: Path) -> None:
    async def no_sleep(delay: float) -> None:
        assert delay >= 0

    trace_dir = tmp_path / "traces"
    provider = ScriptedFakeProvider(
        [
            ProviderRequestError("busy", status_code=503),
            ModelResponse(content="recovered"),
        ]
    )

    result = await _execute(
        provider,
        RunObserver(LoggingConfig(level="DEBUG", trace_dir=trace_dir)),
        provider_retry=ProviderRetry(
            1,
            sleep=no_sleep,
            random_source=lambda: 0.5,
        ),
    )

    assert result == "recovered"
    events = next(iter(_read_runs(trace_dir).values()))
    retry = next(event for event in events if event["event"] == "provider_retry")
    assert retry["level"] == "WARNING"
    assert retry["attempt"] == 1


@pytest.mark.asyncio
async def test_structured_success_emits_validation_event(tmp_path: Path) -> None:
    class Result(BaseModel):
        accepted: bool

    spec = AgentSpec(
        name="structured-observer",
        model_alias="strong",
        instructions="Return a decision.",
        tool_names=(),
        output_model=Result,
        max_steps=2,
        generation=GenerationOptions(),
        source_path=Path("structured.md"),
    )
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[ToolCall("final", FINAL_TOOL_NAME, {"accepted": True})]
            )
        ]
    )
    trace_dir = tmp_path / "traces"

    result = await execute_structured_agent(
        provider=provider,
        spec=spec,
        model=_model(),
        tools=(),
        capabilities=provider.capabilities,
        generation=GenerationOptions(),
        runtime=RuntimeConfig(),
        prompt="Decide",
        observer=RunObserver(LoggingConfig(level="DEBUG", trace_dir=trace_dir)),
    )

    assert result == Result(accepted=True)
    events = next(iter(_read_runs(trace_dir).values()))
    assert "structured_output_validated" in [event["event"] for event in events]


def test_central_redaction_covers_nested_service_account_secrets() -> None:
    secret = "sentinel-private-key"
    source = {
        "credentials": {
            "client_email": "agent@example.test",
            "private_key": secret,
        },
        "message": f"failed using {secret}",
    }
    secrets = collect_secret_values(source)

    assert secrets == (secret, "agent@example.test")
    assert redact(source, secrets=secrets) == {
        "credentials": REDACTED,
        "message": f"failed using {REDACTED}",
    }


def test_trace_directory_is_not_created_when_disabled(tmp_path: Path) -> None:
    observer = RunObserver(LoggingConfig(trace_dir=None))

    observer.emit("run_started", run_id="disabled", level=logging.INFO)

    assert list(tmp_path.iterdir()) == []
