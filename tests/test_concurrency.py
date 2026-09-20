"""Tests for per-run isolation and cooperative cancellation."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path

import pytest

from moiryx import Agent, tool
from moiryx.config import reset_config_cache
from moiryx.errors import AgentProtocolError
from moiryx.messages import AssistantMessage, ToolCall, UserMessage
from moiryx.models import ModelRequest, ModelResponse, ProviderCapabilities
from moiryx.providers import PROVIDER_FACTORIES, ScriptedFakeProvider
from moiryx.tools import GLOBAL_TOOL_REGISTRY


class ConcurrentRepairProvider:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []
        self._first_rounds = 0
        self._both_started = asyncio.Event()

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tool_calling=True)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(deepcopy(request))
        prompt = next(
            message.content
            for message in request.messages
            if isinstance(message, UserMessage)
        )
        has_tool_round = any(
            isinstance(message, AssistantMessage) for message in request.messages
        )
        if has_tool_round:
            return ModelResponse(content=f"done:{prompt}")

        self._first_rounds += 1
        if self._first_rounds == 2:
            self._both_started.set()
        await self._both_started.wait()
        return ModelResponse(tool_calls=[ToolCall(f"{prompt}-bad", "lookup", {})])

    async def close(self) -> None:
        pass


class BlockingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped.set()

    async def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def isolate_runtime() -> None:
    original_factories = dict(PROVIDER_FACTORIES)
    reset_config_cache()
    GLOBAL_TOOL_REGISTRY.clear()
    PROVIDER_FACTORIES.clear()
    yield
    reset_config_cache()
    GLOBAL_TOOL_REGISTRY.clear()
    PROVIDER_FACTORIES.clear()
    PROVIDER_FACTORIES.update(original_factories)


def _write_agent(
    root: Path,
    *,
    tools: str = "[]",
    repair_attempts: int = 1,
) -> tuple[Path, Path]:
    config_path = root / "moiryx.yaml"
    config_path.write_text(
        "providers:\n"
        "  local:\n"
        "    type: openai_compatible\n"
        "    base_url: http://localhost:8080/v1\n"
        "models:\n"
        "  strong:\n"
        "    provider: local\n"
        "    model: local/model-v1\n"
        "runtime:\n"
        f"  tool_call_repair_attempts: {repair_attempts}\n",
        encoding="utf-8",
    )
    agent_path = root / "agent.md"
    agent_path.write_text(
        f"---\nmodel: strong\ntools: {tools}\nmax_steps: 3\n---\nKeep runs isolated.\n",
        encoding="utf-8",
    )
    return config_path, agent_path


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_same_agent_keeps_messages_and_repair_counters_per_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @tool
    def lookup(value: int) -> int:
        return value

    config_path, agent_path = _write_agent(tmp_path, tools="[lookup]")
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    provider = ConcurrentRepairProvider()
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider
    agent = Agent(agent_path)

    results = await asyncio.gather(agent("first"), agent("second"))

    assert results == ["done:first", "done:second"]
    assert len(provider.requests) == 4
    for prompt in ("first", "second"):
        matching = [
            request
            for request in provider.requests
            if any(
                isinstance(message, UserMessage) and message.content == prompt
                for message in request.messages
            )
        ]
        assert len(matching) == 2
        assert all(
            not any(
                isinstance(message, UserMessage) and message.content != prompt
                for message in request.messages
            )
            for request in matching
        )


@pytest.mark.asyncio
async def test_concurrent_runs_receive_distinct_run_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EmptyProvider(ConcurrentRepairProvider):
        async def complete(self, request: ModelRequest) -> ModelResponse:
            self.requests.append(deepcopy(request))
            self._first_rounds += 1
            if self._first_rounds == 2:
                self._both_started.set()
            await self._both_started.wait()
            return ModelResponse()

    config_path, agent_path = _write_agent(tmp_path)
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    provider = EmptyProvider()
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider
    agent = Agent(agent_path)

    results = await asyncio.gather(
        agent("first"),
        agent("second"),
        return_exceptions=True,
    )

    assert all(isinstance(result, AgentProtocolError) for result in results)
    run_ids = {
        result.context["run"]
        for result in results
        if isinstance(result, AgentProtocolError)
    }
    assert len(run_ids) == 2


@pytest.mark.asyncio
async def test_cancelling_agent_cancels_in_flight_provider_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path, agent_path = _write_agent(tmp_path)
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    provider = BlockingProvider()
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider
    agent = Agent(agent_path)
    task = asyncio.create_task(agent("cancel me"))
    await provider.started.wait()

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(provider.stopped.wait(), timeout=1)


@pytest.mark.asyncio
async def test_cancelling_agent_cancels_in_flight_async_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()

    @tool
    async def slow_tool() -> str:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    config_path, agent_path = _write_agent(tmp_path, tools="[slow_tool]")
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    provider = ScriptedFakeProvider(
        [ModelResponse(tool_calls=[ToolCall("slow", "slow_tool", {})])]
    )
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider
    agent = Agent(agent_path)
    task = asyncio.create_task(agent("cancel tool"))
    await started.wait()

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(stopped.wait(), timeout=1)
