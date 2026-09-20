"""Import Pydantic output models referenced by agent definitions."""

from __future__ import annotations

import importlib
from pathlib import Path

from pydantic import BaseModel

from moiryx.errors import AgentDefinitionError


def load_output_model(
    reference: str,
    *,
    agent_path: str | Path,
) -> type[BaseModel]:
    """Load ``module.path:ClassName`` and require a Pydantic model class."""
    error = AgentDefinitionError(
        f"Could not load output model '{reference}' from agent '{agent_path}'."
    )
    module_name, separator, class_name = reference.partition(":")
    if separator != ":" or not module_name or not class_name or ":" in class_name:
        raise error

    try:
        module = importlib.import_module(module_name)
        candidate = getattr(module, class_name)
    except (ImportError, AttributeError) as cause:
        raise error from cause

    if not isinstance(candidate, type) or not issubclass(candidate, BaseModel):
        raise error
    return candidate


__all__ = ["load_output_model"]
