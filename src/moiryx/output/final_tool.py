"""Internal synthetic tool used to return a validated agent result."""

from __future__ import annotations

from typing import Any, NoReturn

from pydantic import BaseModel, TypeAdapter

from moiryx.errors import AgentProtocolError
from moiryx.models import ToolDefinition
from moiryx.tools.registry import FINAL_TOOL_NAME

FINAL_TOOL_DESCRIPTION = (
    "Submit the final structured result after all other tool calls are complete."
)


def _reject_direct_execution(**_: Any) -> NoReturn:
    raise AgentProtocolError("The internal final-result tool cannot be executed")


def build_final_tool(output_model: type[BaseModel]) -> ToolDefinition:
    """Build an internal definition whose parameters are the output model itself."""
    if not isinstance(output_model, type) or not issubclass(output_model, BaseModel):
        raise TypeError("output_model must be a Pydantic BaseModel subclass")
    return ToolDefinition(
        name=FINAL_TOOL_NAME,
        description=FINAL_TOOL_DESCRIPTION,
        function=_reject_direct_execution,
        input_model=output_model,
        return_adapter=TypeAdapter(output_model),
    )


__all__ = ["FINAL_TOOL_DESCRIPTION", "build_final_tool"]
