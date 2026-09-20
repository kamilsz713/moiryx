"""Registry for built-in and explicitly imported custom tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from moiryx.errors import DuplicateToolError, ToolDefinitionError, UnknownToolError
from moiryx.models import ToolDefinition
from moiryx.tools.definition import build_tool_definition

FINAL_TOOL_NAME = "__moiryx_submit_result"
BUILTIN_TOOL_NAMES = frozenset(
    {
        "edit_file",
        "glob_files",
        "grep",
        "list_files",
        "read_file",
        "shell",
        "write_file",
    }
)
RESERVED_TOOL_NAMES = frozenset({FINAL_TOOL_NAME})


class ToolRegistry:
    """Store tool definitions under their exact Python function names."""

    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, function: Callable[..., Any]) -> ToolDefinition:
        """Validate and register a function without replacing existing tools."""
        name = function.__name__
        if not name.isidentifier():
            raise ToolDefinitionError(
                f"Tool name '{name}' must be a valid Python identifier"
            )
        if name in RESERVED_TOOL_NAMES:
            raise ToolDefinitionError(f"Tool name '{name}' is reserved by Moiryx")
        if name in BUILTIN_TOOL_NAMES:
            raise DuplicateToolError(
                "Tool name conflicts with a built-in tool",
                tool_name=name,
            )
        if name in self._definitions:
            raise DuplicateToolError(
                "Tool name is already registered",
                tool_name=name,
            )

        definition = build_tool_definition(function)
        self._definitions[name] = definition
        return definition

    def resolve(self, name: str) -> ToolDefinition:
        """Resolve a tool by exact name."""
        try:
            return self._definitions[name]
        except KeyError:
            raise UnknownToolError(
                "Unknown tool",
                tool_name=name,
            ) from None

    @property
    def names(self) -> tuple[str, ...]:
        """Return registered names in deterministic insertion order."""
        return tuple(self._definitions)

    def clear(self) -> None:
        """Remove all definitions; intended for isolated runtime/test setup."""
        self._definitions.clear()


GLOBAL_TOOL_REGISTRY = ToolRegistry()

__all__ = [
    "BUILTIN_TOOL_NAMES",
    "FINAL_TOOL_NAME",
    "GLOBAL_TOOL_REGISTRY",
    "RESERVED_TOOL_NAMES",
    "ToolRegistry",
]
