"""Executable checks for public documentation, examples, and CI configuration."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from scripts.check_release_tag import check_release_tag

from moiryx.agent_spec import load_agent_spec

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _blocks(text: str, language: str) -> list[str]:
    pattern = rf"```{re.escape(language)}\n(.*?)```"
    return re.findall(pattern, text, flags=re.DOTALL)


def test_readme_leads_with_user_experience_and_covers_public_flows() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text("utf-8")

    assert readme.startswith("# Moiryx\n\nMoiryx lets you define an agent")
    for expected in (
        "## Your first agent with a local llama-server",
        "## Built-in tools",
        "## Custom tools",
        "## Structured output",
        "## Switching providers in YAML",
        "## Logging and traces",
    ):
        assert expected in readme
    assert "sentinel-" not in readme


def test_readme_python_and_yaml_blocks_are_syntactically_valid() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text("utf-8")

    python_blocks = _blocks(readme, "python")
    yaml_blocks = _blocks(readme, "yaml")
    assert python_blocks
    assert yaml_blocks
    for index, source in enumerate(python_blocks):
        compile(source, f"README-python-{index}", "exec")
    for source in yaml_blocks:
        assert isinstance(yaml.safe_load(source), dict)


def test_example_files_parse_and_python_sources_compile() -> None:
    examples = PROJECT_ROOT / "examples"
    config = yaml.safe_load((examples / "moiryx.yaml").read_text("utf-8"))

    assert config["providers"]["local"]["type"] == "openai_compatible"
    assert config["providers"]["router"]["type"] == "openrouter"
    for source_path in examples.glob("*.py"):
        compile(source_path.read_text("utf-8"), str(source_path), "exec")
    specs = [
        load_agent_spec(path, default_max_steps=20)
        for path in sorted((examples / "agents").glob("*.md"))
    ]
    assert {spec.name for spec in specs} == {
        "chat",
        "nested_reviewer",
        "reviewer",
        "word_counter",
        "workspace_editor",
        "workspace_reader",
    }
    assert next(spec for spec in specs if spec.name == "reviewer").output_model
    assert next(spec for spec in specs if spec.name == "nested_reviewer").output_model


def test_ci_matrix_runs_quality_build_and_clean_install_smoke() -> None:
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    workflow_text = workflow_path.read_text("utf-8")
    workflow = yaml.safe_load(workflow_text)

    assert workflow["on"] == {
        "push": None,
        "pull_request": None,
        "workflow_dispatch": None,
    }
    assert workflow["jobs"]["quality"]["strategy"]["matrix"]["python-version"] == [
        "3.11",
        "3.12",
    ]
    assert "python -m pytest -m acceptance -q" in workflow_text
    assert 'python -m pytest -q -m "not integration"' in workflow_text
    assert "python -m ruff check" in workflow_text
    assert "python -m mypy" in workflow_text
    assert "python -m build" in workflow_text
    assert "scripts/audit_artifacts.py dist" in workflow_text
    assert "python -m venv .venv-smoke" in workflow_text
    assert "scripts/smoke_artifact.py" in workflow_text
    assert "actions/upload-artifact@v4" in workflow_text


def test_sdist_manifest_includes_docs_and_examples() -> None:
    manifest = (PROJECT_ROOT / "MANIFEST.in").read_text("utf-8")

    assert "recursive-include docs *.md" in manifest
    assert "recursive-include examples *.md *.py *.yaml" in manifest


def test_publish_workflow_uses_release_tag_and_trusted_publisher() -> None:
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "publish.yml"
    workflow = yaml.safe_load(workflow_path.read_text("utf-8"))

    assert workflow["on"] == {"release": {"types": ["published"]}}
    assert workflow["permissions"] == {"contents": "read"}
    build = workflow["jobs"]["build"]
    publish = workflow["jobs"]["publish"]
    assert any(
        step.get("run") == "python scripts/check_release_tag.py"
        for step in build["steps"]
    )
    assert publish["needs"] == "build"
    assert publish["environment"]["name"] == "pypi"
    assert publish["permissions"] == {"id-token": "write"}
    assert publish["steps"][-1]["uses"] == "pypa/gh-action-pypi-publish@release/v1"


def test_release_tag_must_match_package_version() -> None:
    check_release_tag("v0.1.0a1")
    with pytest.raises(ValueError, match=r"must be 'v0\.1\.0a1'"):
        check_release_tag("v0.1.0")
