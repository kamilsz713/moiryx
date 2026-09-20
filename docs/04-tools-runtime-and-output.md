# Tools, runtime, and structured output

## Custom tools

```python
from moiryx import tool


@tool
async def get_build_status(build_id: int) -> BuildStatus:
    """Return the current CI build status."""
    ...
```

`@tool` returns the original function, registers it under its Python name,
and attaches `__moiryx_tool__` metadata. Registration inspects its signature
and type hints, reads its docstring, builds a Pydantic input model and JSON
schema, and prepares a return-value adapter. Missing annotations, unsupported
parameter kinds (`*args`, `**kwargs`, positional-only), duplicate names, and
the reserved `__moiryx_submit_result` name are rejected.

Arguments are validated before execution. Async functions are awaited; sync
functions run in a worker thread. Each call has a timeout. Results are
serialized to text and visibly truncated at `max_tool_output_chars`. Tool
exceptions and timeouts return a failed `ToolMessage` to the model without a
full traceback. Event status comes from the result, not from parsing its text.

## Whole-batch preflight

Every tool call in a model response is checked before any tool executes:

```text
normalize -> exact name lookup -> conservative argument repair
          -> Pydantic validation -> execute all sequentially, or execute none
```

Allowed repairs are deterministic: trim whitespace around a name, parse a
JSON object, unwrap one obvious double-encoded object or `arguments` wrapper,
and apply input-model coercion. The runtime does not guess a similar tool,
invent missing values, drop unknown fields, or extract arguments from prose.
An unknown name may receive a suggestion, but the model must issue a new call.
Repeated invalid calls consume `tool_call_repair_attempts`; exhaustion raises
`ToolCallRepairError`.

## Built-in tools

Agents receive only built-ins named in their Markdown frontmatter:

| Purpose | Tools |
| --- | --- |
| Read and search | `read_file`, `list_files`, `glob_files`, `grep` |
| Write | `write_file`, `edit_file` |
| Process | `shell` |

File paths are resolved beneath `workspace_root` by default, including
symlinks and junctions. `allow_paths_outside_workspace: true` explicitly
relaxes that policy. `read_file` reads UTF-8 and supports inclusive, one-based
line ranges. `list_files` is non-recursive; `glob_files` accepts only relative
patterns without parent traversal. `grep` uses `rg` when available and a
Python UTF-8 fallback otherwise. `write_file` uses an atomic replacement;
`edit_file` changes a file only if `old_text` occurs exactly once.

`shell` starts in the configured workspace, reports exit code and separate
stdout/stderr, and terminates its process tree on timeout or cancellation.
Unlike the file tools, **it is not a sandbox**: shell commands can access
anything the host user can access. Enable it only for trusted agents.

## Agent loop and structured results

Each model response consumes one agent step. A text agent returns final
content without a wrapper. A response with neither content nor tool calls
raises `AgentProtocolError`; exhausting the step budget raises
`MaxStepsExceeded` rather than returning a partial result.

For structured agents, the declared Pydantic model supplies both the schema
and final validation. With tool calling, Moiryx offers an internal
`__moiryx_submit_result` tool. It must be called exactly once and alone after
ordinary tools finish. Plain JSON text is not accepted as a substitute. When
tool calling is unavailable, guaranteed native structured output may be used
only for an agent without user tools. Otherwise construction raises
`ProviderCapabilityError`. Protocol corrections consume the separate
`structured_output_retries` budget.

Provider retries cover transient transport failures, HTTP 429, and selected
5xx responses with bounded exponential backoff and jitter. They do not retry
bad credentials or invalid requests. Cancellation propagates to the caller.
