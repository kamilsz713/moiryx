"""Public ``@tool`` decorator."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from moiryx.tools.registry import GLOBAL_TOOL_REGISTRY

TOOL_METADATA_ATTRIBUTE = "__moiryx_tool__"
_Function = TypeVar("_Function", bound=Callable[..., Any])


def tool(function: _Function) -> _Function:
    """Register tool metadata while returning the original function unchanged."""
    definition = GLOBAL_TOOL_REGISTRY.register(function)
    setattr(function, TOOL_METADATA_ATTRIBUTE, definition)
    return function


__all__ = ["TOOL_METADATA_ATTRIBUTE", "tool"]
