"""Tests for validated, asynchronous tool execution."""

from __future__ import annotations

import asyncio
import threading

import pytest

from moiryx.errors import ToolExecutionError, ToolTimeoutError, ToolValidationError
from moiryx.tools.definition import build_tool_definition
from moiryx.tools.executor import ToolExecutor


@pytest.mark.asyncio
async def test_arguments_are_validated_before_function_call() -> None:
    calls = 0

    def increment(value: int) -> int:
        nonlocal calls
        calls += 1
        return value + 1

    definition = build_tool_definition(increment)

    with pytest.raises(ToolValidationError, match="tool=increment"):
        await ToolExecutor(1).execute(definition, {"value": "not-an-int"})

    assert calls == 0


@pytest.mark.asyncio
async def test_async_function_is_awaited() -> None:
    async def double(value: int) -> int:
        await asyncio.sleep(0)
        return value * 2

    result = await ToolExecutor(1).execute(
        build_tool_definition(double),
        {"value": 4},
    )

    assert result == 8


@pytest.mark.asyncio
async def test_sync_function_runs_in_a_worker_thread() -> None:
    caller_thread = threading.get_ident()

    def current_thread() -> int:
        return threading.get_ident()

    result = await ToolExecutor(1).execute(build_tool_definition(current_thread), {})

    assert result != caller_thread


@pytest.mark.asyncio
async def test_timeout_and_tool_raised_timeout_are_distinct() -> None:
    async def slow() -> None:
        await asyncio.sleep(1)

    def raises_timeout() -> int:
        raise TimeoutError("raised by the tool")

    with pytest.raises(ToolTimeoutError, match="tool=slow"):
        await ToolExecutor(0.01).execute(build_tool_definition(slow), {})
    with pytest.raises(ToolExecutionError, match="TimeoutError"):
        await ToolExecutor(1).execute(build_tool_definition(raises_timeout), {})


@pytest.mark.asyncio
async def test_execution_error_does_not_expose_exception_message() -> None:
    def explode() -> int:
        raise RuntimeError("sentinel-secret")

    with pytest.raises(ToolExecutionError) as captured:
        await ToolExecutor(1).execute(build_tool_definition(explode), {})

    assert "RuntimeError" in str(captured.value)
    assert "sentinel-secret" not in str(captured.value)


@pytest.mark.asyncio
async def test_cancellation_is_not_wrapped() -> None:
    started = asyncio.Event()

    async def wait_forever() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(
        ToolExecutor(10).execute(build_tool_definition(wait_forever), {})
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize("timeout", (0, -1, True, "1"))
def test_timeout_must_be_a_positive_number(timeout: object) -> None:
    with pytest.raises(ValueError, match="positive number"):
        ToolExecutor(timeout)  # type: ignore[arg-type]
