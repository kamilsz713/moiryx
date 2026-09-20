"""Tests for custom tool registration, metadata, and generated schemas."""

from enum import StrEnum
from typing import Literal

import pytest
from pydantic import BaseModel, Field, ValidationError

from moiryx import tool
from moiryx.errors import DuplicateToolError, ToolDefinitionError, UnknownToolError
from moiryx.models import ToolDefinition
from moiryx.tools import GLOBAL_TOOL_REGISTRY


class SearchMode(StrEnum):
    FAST = "fast"
    DEEP = "deep"


class SearchFilter(BaseModel):
    minimum_score: int = Field(ge=1, le=10)


@pytest.fixture(autouse=True)
def clear_global_registry() -> None:
    GLOBAL_TOOL_REGISTRY.clear()
    yield
    GLOBAL_TOOL_REGISTRY.clear()


def test_decorator_registers_metadata_and_preserves_direct_call() -> None:
    def original(value: int) -> int:
        """Increment a value."""
        return value + 1

    decorated = tool(original)

    assert decorated is original
    assert decorated(1) == 2
    metadata = decorated.__moiryx_tool__  # type: ignore[attr-defined]
    assert isinstance(metadata, ToolDefinition)
    assert metadata.name == "original"
    assert GLOBAL_TOOL_REGISTRY.resolve("original") is metadata


def test_duplicate_and_reserved_names_are_rejected() -> None:
    @tool
    def duplicate(value: int) -> int:
        return value

    with pytest.raises(DuplicateToolError, match="tool=duplicate"):

        @tool
        def duplicate(value: int) -> int:  # type: ignore[no-redef]
            return value

    with pytest.raises(ToolDefinitionError, match="reserved"):

        @tool
        def __moiryx_submit_result(value: int) -> int:
            return value

    with pytest.raises(DuplicateToolError, match=r"built-in.*tool=read_file"):

        @tool
        def read_file(path: str) -> str:
            return path


def test_unknown_tool_uses_exact_lookup() -> None:
    with pytest.raises(UnknownToolError, match="tool=read_flie"):
        GLOBAL_TOOL_REGISTRY.resolve("read_flie")


def test_schema_preserves_types_defaults_and_docstring_descriptions() -> None:
    @tool
    def search(
        query: str,
        limit: int = 10,
        tags: list[str] | None = None,
        mode: Literal["fast", "deep"] = "fast",
        search_filter: SearchFilter | None = None,
        enum_mode: SearchMode = SearchMode.FAST,
    ) -> list[str]:
        """Search indexed project content.

        Args:
            query: Text to search for.
            limit: Maximum number of results.
            tags: Optional tags used to filter results.
            mode: Search strategy.
            search_filter: Nested score constraints.
            enum_mode: Enum-backed execution mode.
        """
        return [query][:limit]

    definition = search.__moiryx_tool__  # type: ignore[attr-defined]
    schema = definition.schema.parameters
    properties = schema["properties"]

    assert definition.description == "Search indexed project content."
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["query"]
    assert properties["query"]["description"] == "Text to search for."
    assert properties["limit"]["default"] == 10
    assert properties["mode"]["enum"] == ["fast", "deep"]
    assert properties["enum_mode"]["$ref"].endswith("/SearchMode")
    assert properties["search_filter"]["anyOf"][0]["$ref"].endswith("/SearchFilter")

    validated = definition.input_model.model_validate(
        {
            "query": "cache",
            "tags": ["python"],
            "search_filter": {"minimum_score": 5},
        }
    )
    assert validated.tags == ["python"]
    assert validated.search_filter.minimum_score == 5
    with pytest.raises(ValidationError):
        definition.input_model.model_validate({"query": "cache", "extra": True})


@pytest.mark.parametrize(
    "factory",
    (
        lambda: lambda value: value,
        lambda: _missing_parameter_annotation,
        lambda: _variadic_args,
        lambda: _variadic_kwargs,
    ),
)
def test_invalid_function_annotations_are_rejected(factory: object) -> None:
    function = factory()  # type: ignore[operator]
    with pytest.raises(ToolDefinitionError):
        tool(function)  # type: ignore[arg-type]


def _missing_parameter_annotation(value) -> int:  # type: ignore[no-untyped-def]
    return int(value)


def _variadic_args(*values: int) -> int:
    return sum(values)


def _variadic_kwargs(**values: int) -> int:
    return sum(values.values())
