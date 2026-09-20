"""Tests for Markdown agent definitions and output model loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from moiryx.agent_spec import load_agent_spec
from moiryx.errors import AgentDefinitionError
from moiryx.models import GenerationOptions
from moiryx.output import load_output_model


def test_frontmatter_is_parsed_and_markdown_body_is_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "reviewer.md"
    path.write_bytes(
        b"---\n"
        b"model: reviewer_reasoning\n"
        b"tools:\n"
        b"  - read_file\n"
        b"max_steps: 7\n"
        b"generation:\n"
        b"  temperature: 0.2\n"
        b"---\n"
        b"\n# Role\n\n  Preserve this spacing.  \n"
    )

    spec = load_agent_spec(path, default_max_steps=20)

    assert spec.name == "reviewer"
    assert spec.model_alias == "reviewer_reasoning"
    assert spec.tool_names == ("read_file",)
    assert spec.max_steps == 7
    assert spec.generation == GenerationOptions(temperature=0.2)
    assert spec.instructions == "\n# Role\n\n  Preserve this spacing.  \n"


def test_explicit_name_and_default_max_steps_are_used(tmp_path: Path) -> None:
    path = tmp_path / "agent.md"
    path.write_text(
        "---\nname: custom-name\nmodel: fast\n---\nInstructions",
        encoding="utf-8",
    )

    spec = load_agent_spec(path, default_max_steps=11)

    assert spec.name == "custom-name"
    assert spec.max_steps == 11
    assert spec.instructions == "Instructions"


def test_markdown_body_preserves_crlf_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "windows-agent.md"
    path.write_bytes(b"---\r\nmodel: fast\r\n---\r\n\r\n# Role\r\nPreserve me.\r\n")

    spec = load_agent_spec(path)

    assert spec.instructions == "\r\n# Role\r\nPreserve me.\r\n"


@pytest.mark.parametrize(
    "content",
    (
        "No frontmatter",
        "---\nname: missing-model\n---\nBody",
        "---\nmodel: 123\n---\nBody",
        "---\nmodel: valid\ntools: read_file\n---\nBody",
        "---\nmodel: valid\nmax_steps: 0\n---\nBody",
        "---\nmodel: valid\ngeneration:\n  frequency_penalty: 1\n---\nBody",
        "---\nmodel: [broken\n---\nBody",
        "---\nmodel: valid\nBody without closing delimiter",
    ),
)
def test_invalid_agent_definitions_have_specific_errors(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "invalid.md"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(AgentDefinitionError, match=r"invalid\.md"):
        load_agent_spec(path)


def test_output_loader_preserves_nested_models_and_constraints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "sample_output_models"
    package.mkdir()
    package.joinpath("__init__.py").write_text(
        "from pydantic import BaseModel, Field\n"
        "class Issue(BaseModel):\n"
        "    severity: int = Field(ge=1, le=5)\n"
        "class Review(BaseModel):\n"
        "    issues: list[Issue]\n"
        "not_a_model = object()\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    model = load_output_model(
        "sample_output_models:Review",
        agent_path="agents/reviewer.md",
    )
    result = model.model_validate({"issues": [{"severity": 4}]})

    assert result.issues[0].severity == 4
    with pytest.raises(ValidationError):
        model.model_validate({"issues": [{"severity": 9}]})


@pytest.mark.parametrize(
    "reference",
    (
        "missing_separator",
        "missing_output_module:Review",
        "sample_output_models:Missing",
        "sample_output_models:not_a_model",
    ),
)
def test_output_loader_errors_include_agent_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reference: str,
) -> None:
    package = tmp_path / "sample_output_models"
    package.mkdir(exist_ok=True)
    package.joinpath("__init__.py").write_text(
        "not_a_model = object()\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(AgentDefinitionError) as captured:
        load_output_model(reference, agent_path="agents/reviewer.md")

    assert reference in str(captured.value)
    assert "agents/reviewer.md" in str(captured.value)
