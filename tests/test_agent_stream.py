"""Public Agent streaming facade tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from moiryx import Agent
from moiryx.config import reset_config_cache
from moiryx.errors import AgentProtocolError
from moiryx.events import AgentFinished, AgentStarted
from moiryx.messages import AssistantMessage, UserMessage
from moiryx.models import ModelResponse
from moiryx.providers import PROVIDER_FACTORIES, ScriptedFakeProvider


@pytest.fixture(autouse=True)
def isolate_provider_registry() -> None:
    original = dict(PROVIDER_FACTORIES)
    reset_config_cache()
    yield
    reset_config_cache()
    PROVIDER_FACTORIES.clear()
    PROVIDER_FACTORIES.update(original)


def _project(root: Path) -> tuple[Path, Path]:
    config = root / "moiryx.yaml"
    config.write_text(
        "providers:\n"
        "  local:\n"
        "    type: openai_compatible\n"
        "    base_url: http://localhost:8080/v1\n"
        "models:\n"
        "  chat:\n"
        "    provider: local\n"
        "    model: local-model\n"
        "extensions:\n"
        "  code:\n"
        "    handler: example:run\n",
        encoding="utf-8",
    )
    agent = root / "agent.md"
    agent.write_text("---\nmodel: chat\n---\nBe concise.\n", encoding="utf-8")
    return config, agent


@pytest.mark.asyncio
async def test_agent_stream_yields_lifecycle_and_preserves_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, agent_path = _project(tmp_path)
    monkeypatch.setenv("MOIRYX_CONFIG", str(config))
    provider = ScriptedFakeProvider([ModelResponse(content="current")])
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider
    agent = Agent(agent_path)

    events = [
        event
        async for event in agent.stream(
            "Now",
            history=[UserMessage("Earlier"), AssistantMessage("Previous")],
        )
    ]

    assert [type(event) for event in events] == [AgentStarted, AgentFinished]
    assert events[-1].result == "current"
    assert [message.content.strip() for message in provider.requests[0].messages] == [
        "Be concise.",
        "Earlier",
        "Previous",
        "Now",
    ]
    await agent.aclose()


@pytest.mark.asyncio
async def test_agent_stream_emits_failed_terminal_event_then_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, agent_path = _project(tmp_path)
    monkeypatch.setenv("MOIRYX_CONFIG", str(config))
    provider = ScriptedFakeProvider([ModelResponse()])
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider
    agent = Agent(agent_path)
    events = []

    with pytest.raises(AgentProtocolError):
        async for event in agent.stream("Fail"):
            events.append(event)

    assert isinstance(events[0], AgentStarted)
    assert isinstance(events[-1], AgentFinished)
    assert events[-1].status == "failed"
    await agent.aclose()
