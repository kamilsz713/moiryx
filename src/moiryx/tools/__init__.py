"""Custom tool declaration and registry infrastructure."""

from moiryx.tools.builtin import (
    WorkspacePathError,
    WorkspacePathGuard,
    build_builtin_tool,
)
from moiryx.tools.decorator import TOOL_METADATA_ATTRIBUTE, tool
from moiryx.tools.executor import ToolExecutor
from moiryx.tools.preflight import (
    PreparedToolCall,
    RepairFeedback,
    ToolBatchPreflight,
    ToolCallIssue,
    ToolRepairTracker,
    build_repair_feedback,
    execute_prepared_batch,
    preflight_tool_calls,
)
from moiryx.tools.registry import (
    BUILTIN_TOOL_NAMES,
    FINAL_TOOL_NAME,
    GLOBAL_TOOL_REGISTRY,
    RESERVED_TOOL_NAMES,
    ToolRegistry,
)
from moiryx.tools.serialization import build_tool_message, serialize_tool_result

__all__ = [
    "BUILTIN_TOOL_NAMES",
    "FINAL_TOOL_NAME",
    "GLOBAL_TOOL_REGISTRY",
    "RESERVED_TOOL_NAMES",
    "TOOL_METADATA_ATTRIBUTE",
    "PreparedToolCall",
    "RepairFeedback",
    "ToolBatchPreflight",
    "ToolCallIssue",
    "ToolExecutor",
    "ToolRegistry",
    "ToolRepairTracker",
    "WorkspacePathError",
    "WorkspacePathGuard",
    "build_builtin_tool",
    "build_repair_feedback",
    "build_tool_message",
    "execute_prepared_batch",
    "preflight_tool_calls",
    "serialize_tool_result",
    "tool",
]
