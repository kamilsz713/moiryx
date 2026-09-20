"""Parsing and validation of Markdown agent definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from moiryx.errors import AgentDefinitionError, ConfigurationError
from moiryx.generation import merge_generation_options
from moiryx.models import GenerationOptions
from moiryx.output import load_output_model


class _AgentFrontmatter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)] | None = None
    tools: list[str] = Field(default_factory=list)
    output: Annotated[str, Field(min_length=1)] | None = None
    max_steps: Annotated[int, Field(gt=0)] | None = None
    generation: dict[str, object] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Validated, provider-independent definition of an agent."""

    name: str
    model_alias: str
    instructions: str
    tool_names: tuple[str, ...]
    output_model: type[BaseModel] | None
    max_steps: int
    generation: GenerationOptions
    source_path: Path = field(repr=False, compare=False)


def _split_frontmatter(text: str, *, agent_path: Path) -> tuple[object, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text

    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        ),
        None,
    )
    if closing_index is None:
        raise AgentDefinitionError(
            f"Agent definition '{agent_path}' has unclosed YAML frontmatter"
        )

    frontmatter_text = "".join(lines[1:closing_index])
    body = "".join(lines[closing_index + 1 :])
    try:
        frontmatter: object = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = (
            f" at line {mark.line + 2}, column {mark.column + 1}"
            if mark is not None
            else ""
        )
        raise AgentDefinitionError(
            f"Invalid YAML frontmatter in agent '{agent_path}'{location}"
        ) from error

    return ({} if frontmatter is None else frontmatter), body


def _validation_summary(error: ValidationError) -> str:
    issues: list[str] = []
    for item in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = ".".join(str(part) for part in item["loc"])
        prefix = f"{location}: " if location else ""
        issues.append(f"{prefix}{item['msg']}")
    return "; ".join(issues)


def load_agent_spec(
    agent_file: str | Path,
    *,
    default_max_steps: int = 20,
) -> AgentSpec:
    """Read and fully validate one Markdown agent definition."""
    agent_path = Path(agent_file)
    if (
        isinstance(default_max_steps, bool)
        or not isinstance(default_max_steps, int)
        or default_max_steps <= 0
    ):
        raise AgentDefinitionError(
            "default_max_steps must be a positive integer",
        )

    try:
        with agent_path.open("r", encoding="utf-8", newline="") as source:
            text = source.read()
    except (OSError, UnicodeError) as error:
        raise AgentDefinitionError(
            f"Could not read agent definition '{agent_path}': {type(error).__name__}"
        ) from error

    raw_frontmatter, instructions = _split_frontmatter(text, agent_path=agent_path)
    if not isinstance(raw_frontmatter, Mapping):
        raise AgentDefinitionError(
            f"YAML frontmatter in agent '{agent_path}' must be a mapping"
        )

    try:
        frontmatter = _AgentFrontmatter.model_validate(raw_frontmatter)
    except ValidationError as error:
        raise AgentDefinitionError(
            f"Invalid agent definition '{agent_path}': {_validation_summary(error)}"
        ) from error

    try:
        generation = merge_generation_options(agent=frontmatter.generation)
    except ConfigurationError as error:
        raise AgentDefinitionError(
            f"Invalid agent definition '{agent_path}': {error.message}"
        ) from error

    output_model = (
        load_output_model(frontmatter.output, agent_path=agent_path)
        if frontmatter.output is not None
        else None
    )
    return AgentSpec(
        name=frontmatter.name or agent_path.stem,
        model_alias=frontmatter.model,
        instructions=instructions,
        tool_names=tuple(frontmatter.tools),
        output_model=output_model,
        max_steps=frontmatter.max_steps or default_max_steps,
        generation=generation,
        source_path=agent_path,
    )


__all__ = ["AgentSpec", "load_agent_spec"]
