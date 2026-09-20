"""Build tool metadata and schemas from Python functions."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar, get_type_hints

from docstring_parser import parse
from pydantic import ConfigDict, Field, TypeAdapter, create_model

from moiryx.errors import ToolDefinitionError
from moiryx.models import ToolDefinition

_Function = TypeVar("_Function", bound=Callable[..., Any])
_UNSUPPORTED_PARAMETER_KINDS = {
    inspect.Parameter.POSITIONAL_ONLY,
    inspect.Parameter.VAR_POSITIONAL,
    inspect.Parameter.VAR_KEYWORD,
}


def build_tool_definition(function: _Function) -> ToolDefinition:
    """Create validated metadata, input model, schema, and return adapter."""
    name = function.__name__
    try:
        signature = inspect.signature(function)
        type_hints = get_type_hints(function, include_extras=True)
    except (NameError, TypeError, ValueError) as error:
        raise ToolDefinitionError(
            f"Could not inspect tool '{name}' type annotations"
        ) from error

    raw_docstring = inspect.getdoc(function) or ""
    parsed_docstring = parse(raw_docstring)
    description = parsed_docstring.short_description or ""
    parameter_descriptions = {
        parameter.arg_name: parameter.description
        for parameter in parsed_docstring.params
        if parameter.arg_name and parameter.description
    }

    fields: dict[str, Any] = {}
    for parameter_name, parameter in signature.parameters.items():
        if parameter.kind in _UNSUPPORTED_PARAMETER_KINDS:
            raise ToolDefinitionError(
                f"Tool '{name}' has unsupported parameter '{parameter_name}' "
                f"of kind {parameter.kind.description}"
            )
        if parameter_name not in type_hints:
            raise ToolDefinitionError(
                f"Tool '{name}' parameter '{parameter_name}' is missing a type annotation"
            )

        default = (
            ... if parameter.default is inspect.Parameter.empty else parameter.default
        )
        description_for_parameter = parameter_descriptions.get(parameter_name)
        if description_for_parameter:
            default = Field(default=default, description=description_for_parameter)
        fields[parameter_name] = (type_hints[parameter_name], default)

    if "return" not in type_hints:
        raise ToolDefinitionError(f"Tool '{name}' is missing a return type annotation")

    model_name = f"{name}Input"
    try:
        input_model = create_model(
            model_name,
            __config__=ConfigDict(extra="forbid"),
            __module__=function.__module__,
            **fields,
        )
        return_adapter = TypeAdapter(type_hints["return"])
    except (TypeError, ValueError) as error:
        raise ToolDefinitionError(
            f"Could not create schema for tool '{name}'"
        ) from error

    return ToolDefinition(
        name=name,
        description=description,
        function=function,
        input_model=input_model,
        return_adapter=return_adapter,
    )


__all__ = ["build_tool_definition"]
