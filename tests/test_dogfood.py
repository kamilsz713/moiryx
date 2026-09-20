"""Offline user-path dogfood through the public Agent and @tool API."""

from __future__ import annotations

from pathlib import Path

import pytest
from examples.models import NestedReviewResult

from moiryx import Agent, tool
from moiryx.config import reset_config_cache
from moiryx.messages import ToolCall, ToolMessage
from moiryx.models import ModelResponse
from moiryx.providers import PROVIDER_FACTORIES, ScriptedFakeProvider
from moiryx.tools import FINAL_TOOL_NAME, GLOBAL_TOOL_REGISTRY

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "agents"


@pytest.fixture(autouse=True)
def isolate_runtime() -> None:
    original_factories = dict(PROVIDER_FACTORIES)
    reset_config_cache()
    GLOBAL_TOOL_REGISTRY.clear()
    yield
    reset_config_cache()
    GLOBAL_TOOL_REGISTRY.clear()
    PROVIDER_FACTORIES.clear()
    PROVIDER_FACTORIES.update(original_factories)


def _write_config(root: Path, *, provider: str = "local") -> Path:
    config_path = root / "moiryx.yaml"
    config_path.write_text(
        "\n".join(
            (
                "providers:",
                "  local:",
                "    type: openai_compatible",
                "    base_url: http://127.0.0.1:8080/v1",
                "  router:",
                "    type: openrouter",
                "models:",
                "  local_chat:",
                f"    provider: {provider}",
                f"    model: {provider}/model-v1",
                "runtime:",
                f"  workspace_root: {root.as_posix()}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return config_path


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_dogfood_text_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MOIRYX_CONFIG", str(_write_config(tmp_path)))
    provider = ScriptedFakeProvider([ModelResponse(content="Done.")])
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider

    result = await Agent(EXAMPLES / "chat.md")("Say one word")

    assert result == "Done."
    assert provider.requests[0].model == "local/model-v1"
    assert provider.requests[0].tools == []


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_dogfood_coding_agent_reads_and_edits_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "calc.py"
    source.write_text("def answer():\n    return 1\n", encoding="utf-8")
    monkeypatch.setenv("MOIRYX_CONFIG", str(_write_config(tmp_path)))
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[ToolCall("read", "read_file", {"path": "calc.py"})]
            ),
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        "edit",
                        "edit_file",
                        {
                            "path": "calc.py",
                            "old_text": "return 1",
                            "new_text": "return 2",
                        },
                    )
                ]
            ),
            ModelResponse(content="Changed the return value to 2."),
        ]
    )
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider

    result = await Agent(EXAMPLES / "workspace_editor.md")("Change the result to 2")

    assert result == "Changed the return value to 2."
    assert source.read_text(encoding="utf-8") == "def answer():\n    return 2\n"
    assert [schema.name for schema in provider.requests[0].tools] == [
        "read_file",
        "edit_file",
    ]
    assert isinstance(provider.requests[1].messages[-1], ToolMessage)
    assert provider.requests[1].messages[-1].content.replace("\r\n", "\n") == (
        "def answer():\n    return 1\n"
    )


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_dogfood_custom_tool_integration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    @tool
    async def word_count(text: str) -> int:
        """Count words in an external text payload."""
        return len(text.split())

    monkeypatch.setenv("MOIRYX_CONFIG", str(_write_config(tmp_path)))
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[ToolCall("count", "word_count", {"text": "one two three"})]
            ),
            ModelResponse(content="3 words"),
        ]
    )
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider

    result = await Agent(EXAMPLES / "word_counter.md")("Count: one two three")

    assert result == "3 words"
    assert isinstance(provider.requests[1].messages[-1], ToolMessage)
    assert provider.requests[1].messages[-1].content == "3"


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_dogfood_nested_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MOIRYX_CONFIG", str(_write_config(tmp_path)))
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        "final",
                        FINAL_TOOL_NAME,
                        {
                            "accepted": False,
                            "findings": [
                                {
                                    "path": "calc.py",
                                    "line": 2,
                                    "message": "Zero is not handled.",
                                }
                            ],
                        },
                    )
                ]
            )
        ]
    )
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider

    result = await Agent(EXAMPLES / "nested_reviewer.md")("Review calc.py")

    assert isinstance(result, NestedReviewResult)
    assert result.findings[0].path == "calc.py"
    assert result.findings[0].line == 2
    assert result.findings[0].message == "Zero is not handled."


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_dogfood_switches_provider_by_config_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("MOIRYX_CONFIG", str(config_path))
    local = ScriptedFakeProvider([ModelResponse(content="local")])
    router = ScriptedFakeProvider([ModelResponse(content="router")])
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: local
    PROVIDER_FACTORIES["openrouter"] = lambda config: router
    agent_file = EXAMPLES / "chat.md"

    assert await Agent(agent_file)("The same prompt") == "local"
    _write_config(tmp_path, provider="router")
    reset_config_cache()
    assert await Agent(agent_file)("The same prompt") == "router"

    assert local.requests[0].model == "local/model-v1"
    assert router.requests[0].model == "router/model-v1"
    assert local.requests[0].messages == router.requests[0].messages


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_dogfood_unknown_tool_requires_a_corrected_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    @tool
    def word_count(text: str) -> int:
        """Count words in text."""
        calls.append(text)
        return len(text.split())

    monkeypatch.setenv("MOIRYX_CONFIG", str(_write_config(tmp_path)))
    provider = ScriptedFakeProvider(
        [
            ModelResponse(
                tool_calls=[ToolCall("bad", "word_counts", {"text": "one two"})]
            ),
            ModelResponse(
                tool_calls=[ToolCall("good", "word_count", {"text": "one two"})]
            ),
            ModelResponse(content="2 words"),
        ]
    )
    PROVIDER_FACTORIES["openai_compatible"] = lambda config: provider

    result = await Agent(EXAMPLES / "word_counter.md")("Count: one two")

    assert result == "2 words"
    assert calls == ["one two"]
    bad_feedback = next(
        message
        for message in provider.requests[1].messages
        if isinstance(message, ToolMessage) and message.tool_call_id == "bad"
    )
    assert "word_count" in bad_feedback.content
    assert bad_feedback.content != "2"
    assert isinstance(provider.requests[2].messages[-1], ToolMessage)
    assert provider.requests[2].messages[-1].tool_call_id == "good"
