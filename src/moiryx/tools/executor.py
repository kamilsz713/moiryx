"""Validated and cancellable execution of custom tools."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from moiryx.errors import (
    BuiltinToolError,
    ToolExecutionError,
    ToolTimeoutError,
    ToolValidationError,
)
from moiryx.models import ToolDefinition


class _ToolRaised(Exception):
    """Keep a tool-raised TimeoutError distinct from an executor timeout."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        super().__init__(type(error).__name__)


class ToolExecutor:
    """Validate arguments and execute sync or async tool functions."""

    __slots__ = ("_timeout_seconds",)

    def __init__(self, timeout_seconds: int | float) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive number")
        self._timeout_seconds = float(timeout_seconds)

    async def execute(
        self,
        definition: ToolDefinition,
        arguments: Mapping[str, Any],
    ) -> Any:
        """Validate one call and execute it within the configured timeout."""
        try:
            validated = definition.input_model.model_validate(arguments)
        except ValidationError as error:
            raise ToolValidationError(
                "Tool arguments failed validation",
                tool_name=definition.name,
            ) from error

        return await self.execute_validated(definition, validated)

    async def execute_validated(
        self,
        definition: ToolDefinition,
        arguments: BaseModel,
    ) -> Any:
        """Execute arguments already validated by a whole-batch preflight."""
        if not isinstance(arguments, definition.input_model):
            raise TypeError("arguments must be validated by the tool input model")
        keyword_arguments = {
            name: getattr(arguments, name)
            for name in definition.input_model.model_fields
        }

        async def invoke() -> Any:
            try:
                if inspect.iscoroutinefunction(definition.function):
                    result = await definition.function(**keyword_arguments)
                else:
                    result = await asyncio.to_thread(
                        definition.function,
                        **keyword_arguments,
                    )
                if inspect.isawaitable(result):
                    return await result
                return result
            except asyncio.CancelledError:
                raise
            except Exception as error:
                raise _ToolRaised(error) from error

        try:
            return await asyncio.wait_for(invoke(), timeout=self._timeout_seconds)
        except _ToolRaised as wrapped:
            if isinstance(wrapped.error, BuiltinToolError):
                raise ToolExecutionError(
                    wrapped.error.message,
                    tool_name=definition.name,
                ) from wrapped.error
            raise ToolExecutionError(
                f"Tool execution failed with {type(wrapped.error).__name__}",
                tool_name=definition.name,
            ) from wrapped.error
        except TimeoutError as error:
            raise ToolTimeoutError(
                f"Tool execution exceeded {self._timeout_seconds:g} seconds",
                tool_name=definition.name,
            ) from error


__all__ = ["ToolExecutor"]
