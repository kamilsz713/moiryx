"""Tests for eager Agent construction and capability validation."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from moiryx import Agent, tool
from moiryx.config import ProviderConfig, reset_config_cache
from moiryx.errors import (
    ProviderCapabilityError,
    ProviderNotFoundError,
    UnknownModelError,
    UnknownToolError,
)
from moiryx.messages import SystemMessage, ToolCall, ToolMessage, UserMessage
from moiryx.models import ModelRequest, ModelResponse, ProviderCapabilities
from moiryx.providers import PROVIDER_FACTORIES, ScriptedFakeProvider
from moiryx.tools import FINAL_TOOL_NAME, GLOBAL_TOOL_REGISTRY


class FakeProvider:
    def __init__(
        self,
        config: ProviderConfig,
        capabilities: ProviderCapabilities,
    ) -> None:
        self.config = config
        self._capabilities = capabilities

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise AssertionError(f"Unexpected request for {request.model}")

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


def _write_files(
    root: Path,
    *,
    model_alias: str = "strong",
    provider_alias: str = "local",
    provider_capabilities: str = "",
    tools: str = "[]",
    output: str = "",
) -> tuple[Path, Path]:
    config_path = root / "moiryx.yaml"
    config_path.write_text(
        "\n".join(
            (
                "providers:",
                f"  {provider_alias}:",
                "    type: openai_compatible",
                "    base_url: http://localhost:8080/v1",
                provider_capabilities,
                "models:",
                "  strong:",
                f"    provider: {provider_alias}",
                "    model: local/model-v1",
                "    generation:",
                "      temperature: 0.2",
                "      max_tokens: 100",
                "runtime:",
                "  default_max_steps: 12",
                "  generation:",
                "    temperature: 0.1",
                "    top_p: 0.8",
            )
        ),
        encoding="utf-8",
    )
    agent_path = root / "reviewer.md"
    agent_path.write_text(
        "\n".join(
            (
                "---",
                f"model: {model_alias}",
                f"tools: {tools}",
                output,
                "generation:",
                "  temperature: 0.3",
                "---",
                "Review the input.",
            )
        ),
        encoding="utf-8",
    )
    return config_path, agent_path


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    config_path: Path,
    capabilities: ProviderCapabilities,
) -> None:
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: FakeProvider(
        config,
        capabilities,
    )


def test_constructor_eagerly_resolves_dependencies_without_run_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_module = tmp_path / "agent_schema.py"
    schema_module.write_text(
        "from pydantic import BaseModel\n"
        "class Review(BaseModel):\n"
        "    accepted: bool\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    @tool
    def lookup(issue: int) -> str:
        """Look up an issue."""
        return str(issue)

    config_path, agent_path = _write_files(
        tmp_path,
        tools="[lookup]",
        output="output: agent_schema:Review",
    )
    _configure(
        monkeypatch,
        config_path,
        ProviderCapabilities(tool_calling=True, parallel_tool_calls=True),
    )

    agent = Agent(agent_path)
    prepared = agent._prepared

    assert list(inspect.signature(Agent).parameters) == ["agent_file"]
    assert not hasattr(agent, "__dict__")
    assert prepared.spec.name == "reviewer"
    assert prepared.spec.output_model is not None
    assert prepared.spec.output_model.__name__ == "Review"
    assert prepared.model.alias == "strong"
    assert prepared.model.provider == "local"
    assert prepared.model.model == "local/model-v1"
    assert [definition.name for definition in prepared.tools] == ["lookup"]
    assert prepared.capabilities.tool_calling is True
    assert prepared.capabilities.parallel_tool_calls is True
    assert prepared.generation.temperature == 0.3
    assert prepared.generation.max_tokens == 100
    assert prepared.generation.top_p == 0.8
    assert prepared.spec.max_steps == 12
    assert not hasattr(agent, "messages")
    assert not hasattr(agent, "step")


def test_unknown_tool_stops_construction_before_provider_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path, agent_path = _write_files(tmp_path, tools="[missing]")
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    created = 0

    def factory(config: ProviderConfig) -> FakeProvider:
        nonlocal created
        created += 1
        return FakeProvider(config, ProviderCapabilities(tool_calling=True))

    PROVIDER_FACTORIES["openai_compatible"] = factory

    with pytest.raises(UnknownToolError, match="tool=missing"):
        Agent(agent_path)

    assert created == 0


def test_unknown_model_has_specific_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path, agent_path = _write_files(tmp_path, model_alias="missing")
    _configure(monkeypatch, config_path, ProviderCapabilities())

    with pytest.raises(UnknownModelError, match="model=missing"):
        Agent(agent_path)


def test_unknown_provider_has_specific_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path, agent_path = _write_files(tmp_path, provider_alias="missing")
    config_path.write_text(
        "models:\n  strong:\n    provider: missing\n    model: local/model-v1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))

    with pytest.raises(ProviderNotFoundError, match="provider=missing"):
        Agent(agent_path)


def test_missing_tool_calling_capability_fails_before_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @tool
    def lookup(issue: int) -> str:
        return str(issue)

    config_path, agent_path = _write_files(tmp_path, tools="[lookup]")
    _configure(monkeypatch, config_path, ProviderCapabilities())

    with pytest.raises(ProviderCapabilityError, match="tool-calling"):
        Agent(agent_path)


def test_config_can_override_adapter_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @tool
    def lookup(issue: int) -> str:
        return str(issue)

    config_path, agent_path = _write_files(
        tmp_path,
        tools="[lookup]",
        provider_capabilities="    capabilities:\n      tool_calling: true",
    )
    _configure(monkeypatch, config_path, ProviderCapabilities())

    assert Agent(agent_path)._prepared.capabilities.tool_calling is True


def test_builtin_tools_resolve_only_when_selected_in_agent_definition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path, agent_path = _write_files(
        tmp_path,
        tools="[read_file, list_files, glob_files, grep, write_file, edit_file, shell]",
    )
    _configure(monkeypatch, config_path, ProviderCapabilities(tool_calling=True))

    agent = Agent(agent_path)

    assert [definition.name for definition in agent._prepared.tools] == [
        "read_file",
        "list_files",
        "glob_files",
        "grep",
        "write_file",
        "edit_file",
        "shell",
    ]
    assert GLOBAL_TOOL_REGISTRY.names == ()


@pytest.mark.asyncio
async def test_text_agent_call_delegates_to_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path, agent_path = _write_files(tmp_path)
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    provider = ScriptedFakeProvider([ModelResponse(content="finished")])
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider

    agent = Agent(agent_path)

    assert await agent("Review this") == "finished"
    assert isinstance(provider.requests[0].messages[0], SystemMessage)
    assert isinstance(provider.requests[0].messages[1], UserMessage)
    assert provider.requests[0].messages[1].content == "Review this"
    assert provider.requests[0].tools == []


@pytest.mark.asyncio
async def test_agent_can_close_its_provider_without_requiring_a_context_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path, agent_path = _write_files(tmp_path)
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    provider = ScriptedFakeProvider([ModelResponse(content="finished")])
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider

    async with Agent(agent_path) as agent:
        assert await agent("Review this") == "finished"
        assert not provider.closed

    assert provider.closed
    assert provider.close_calls == 1
    await agent.aclose()
    assert provider.close_calls == 1


@pytest.mark.asyncio
async def test_agent_applies_trace_configuration_and_secret_redaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sentinel-agent-secret"
    trace_dir = tmp_path / "traces"
    config_path, agent_path = _write_files(tmp_path)
    config_text = config_path.read_text(encoding="utf-8")
    config_text = config_text.replace(
        "    base_url: http://localhost:8080/v1",
        f"    base_url: http://localhost:8080/v1\n    api_key: {secret}",
    )
    config_text += (
        "\nlogging:\n"
        "  level: DEBUG\n"
        f"  trace_dir: {trace_dir.as_posix()}\n"
        "  include_raw_response: true\n"
    )
    config_path.write_text(config_text, encoding="utf-8")
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                content="finished",
                raw={"Authorization": f"Bearer {secret}", "echo": secret},
            )
        ]
    )
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider

    assert await Agent(agent_path)("Review this") == "finished"

    trace_path = next(trace_dir.glob("*/events.jsonl"))
    trace = trace_path.read_text("utf-8")
    assert '"event":"run_started"' in trace
    assert '"event":"run_completed"' in trace
    assert '"raw_response"' in trace
    assert secret not in trace


@pytest.mark.asyncio
async def test_agent_executes_selected_builtin_read_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "note.txt").write_text("built-in contents", encoding="utf-8")
    config_path, agent_path = _write_files(tmp_path, tools="[read_file]")
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "runtime:\n",
            f"runtime:\n  workspace_root: {tmp_path.as_posix()}\n",
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[ToolCall("read", "read_file", {"path": "note.txt"})]
            ),
            ModelResponse(content="final answer"),
        ]
    )
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider

    result = await Agent(agent_path)("Read the note")

    assert result == "final answer"
    message = provider.requests[1].messages[-1]
    assert isinstance(message, ToolMessage)
    assert message.name == "read_file"
    assert message.content == "built-in contents"


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_structured_agent_call_returns_declared_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_module = tmp_path / "runtime_agent_schema.py"
    schema_module.write_text(
        "from pydantic import BaseModel, Field\n"
        "class Review(BaseModel):\n"
        "    accepted: bool\n"
        "    score: float = Field(ge=0, le=1)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    config_path, agent_path = _write_files(
        tmp_path,
        output="output: runtime_agent_schema:Review",
    )
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        "final",
                        FINAL_TOOL_NAME,
                        {"accepted": True, "score": 0.9},
                    )
                ]
            )
        ]
    )
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider

    agent = Agent(agent_path)
    output_model = agent._prepared.spec.output_model
    result = await agent("Review this")

    assert output_model is not None
    assert type(result) is output_model
    assert result.model_dump() == {"accepted": True, "score": 0.9}


def test_structured_agent_without_capability_fails_before_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_module = tmp_path / "unsupported_agent_schema.py"
    schema_module.write_text(
        "from pydantic import BaseModel\n"
        "class Review(BaseModel):\n"
        "    accepted: bool\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    config_path, agent_path = _write_files(
        tmp_path,
        output="output: unsupported_agent_schema:Review",
    )
    _configure(monkeypatch, config_path, ProviderCapabilities())

    with pytest.raises(ProviderCapabilityError, match="Structured output"):
        Agent(agent_path)
