"""Factories for built-in tools bound to one prepared agent."""

from __future__ import annotations

from moiryx.config import RuntimeConfig
from moiryx.models import ToolDefinition
from moiryx.tools.builtin.filesystem import build_filesystem_tool
from moiryx.tools.builtin.shell import build_shell_tool
from moiryx.tools.builtin.workspace import WorkspacePathError, WorkspacePathGuard
from moiryx.tools.registry import BUILTIN_TOOL_NAMES


def build_builtin_tool(
    name: str,
    runtime: RuntimeConfig,
) -> ToolDefinition | None:
    """Build a configured built-in definition, or return None for custom lookup."""
    if name not in BUILTIN_TOOL_NAMES:
        return None
    guard = WorkspacePathGuard(
        runtime.workspace_root,
        allow_outside=runtime.allow_paths_outside_workspace,
    )
    filesystem = build_filesystem_tool(name, guard)
    if filesystem is not None:
        return filesystem
    return build_shell_tool(
        guard,
        default_timeout=runtime.tool_timeout_seconds,
        max_output_chars=runtime.max_tool_output_chars,
    )


__all__ = [
    "WorkspacePathError",
    "WorkspacePathGuard",
    "build_builtin_tool",
]
