# Moiryx v0.1 contract

Moiryx is a thin, configuration-driven Python runtime for LLM agents.
Application code owns orchestration; Moiryx owns provider calls, tool
validation and execution, retries, structured results, and diagnostics. This
document records the requirements that must remain stable throughout the
alpha. Focused implementation details live in the [documentation index](README.md).

## User-facing contract

```python
from moiryx import Agent, tool

reviewer = Agent("agents/reviewer.md")
result = await reviewer("Review src/cache.py")
```

`Agent` accepts one agent-definition path. Its constructor resolves the file,
configuration, model alias, provider, selected tools, optional Pydantic output
model, generation options, and capability requirements before the first model
request. A call without `output` returns final `str`; one with `output`
returns an instance of the declared `BaseModel` subclass, without a wrapper.
`@tool` registers the original callable under its Python function name.

Each invocation has a fresh `RunContext` and no implicit memory. Concurrent
calls on one `Agent` do not share messages or retry counters. The main API
needs no context manager, but `await agent.aclose()` and `async with Agent(...)`
provide explicit provider cleanup for long-lived applications.

## Configuration and agent files

The `MOIRYX_CONFIG` environment variable overrides `./moiryx.yaml`; there is
no parent-directory search or multi-file merge. YAML maps provider aliases to
connections and model aliases to provider/model IDs. Model IDs are opaque,
including slashes. `${NAME}` interpolation requires the named environment
variable. Config validation does not expose secret values in diagnostics.

An agent file begins with YAML frontmatter and uses its Markdown body as
system instructions:

```markdown
---
model: local_chat
tools: [read_file]
output: my_app.schemas:Review
max_steps: 15
---
Review the implementation and return concrete findings.
```

`model` is required. `name` defaults to the file stem, `tools` to an empty
list, and `max_steps` to the runtime default. `generation` settings merge in
runtime → model → agent order. Only declared tools are exposed. Import paths
for custom tools are listed in `tool_modules`; the runtime does not scan files.

## Provider boundary

An adapter translates normalized `ModelRequest` and `ModelResponse` values to
and from its API or SDK. It exposes tool-calling, guaranteed native structured
output, and parallel-tool-call capabilities. Tool-call ID, name, parsed
arguments, raw arguments, and parse errors must survive normalization; a
malformed call should reach the shared repair layer rather than fail silently
in an adapter. SDK types must not leak into the core API.

Required v0.1 types are `openai_compatible`, `openrouter`, `azure_openai`,
`azure_foundry`, and `vertex_ai`. OpenAI-compatible endpoints are first-class
local targets. Vertex AI uses ADC or service-account environment credentials
through its optional Google dependency. Provider retries cover transient
transport failures, HTTP 429, and selected 5xx responses, with bounded
backoff. Invalid credentials, models, requests, and configurations do not get
automatic retries or hidden fallback to another provider.

## Tools and execution

Tool signatures and type hints define Pydantic input schemas; missing
annotations, unsupported parameter kinds, duplicate names, and unknown tools
are errors. Sync and async functions are supported with a per-call timeout.
Results are serialized within an explicit output limit; truncation is marked.

Before any tool executes, **every** call in a response is normalized, resolved
by exact name, conservatively repaired where unambiguous, and validated.
One invalid call means none of the batch executes. The model receives bounded
feedback and must issue a corrected call. Never fuzzy-execute a similar tool,
invent missing arguments, or silently discard unknown fields. Valid calls
execute sequentially in model order in v0.1. Provider retries, tool-call
repairs, structured-result repairs, and agent steps have independent limits.

Built-ins are `read_file`, `list_files`, `glob_files`, `grep`, `write_file`,
`edit_file`, and `shell`. File operations stay beneath `workspace_root` by
default; writes are atomic and edits require exactly one match. `shell` is
explicitly selected and **not a security sandbox**: its commands run with the
host user's permissions despite timeouts and output bounds.

## Final results and failure behavior

A text agent returns the last model content when no tool calls remain. A
response with neither text nor calls is a protocol error; hitting `max_steps`
raises `MaxStepsExceeded`, never a partial success.

For structured agents, the declared Pydantic model defines schema and final
validation. With tool calling, the reserved `__moiryx_submit_result` tool is
called once and alone. Without tool calling, guaranteed native structured
output is allowed only when the agent has no user tools. Plain text or JSON
inside Markdown is not parsed into a structured result. Unsupported
capabilities, invalid final calls, and exhausted correction budgets have
explicit errors.

Cancellation propagates. Moiryx does not silently compress prompts, change
models, add tools, or reinterpret invalid schemas. Prefer a clear exception
to a guessed success.

## Acceptance criteria

| ID | Required behavior |
| --- | --- |
| AC1 | A text agent without tools returns final text. |
| AC2 | An agent can read and edit through selected built-in tools. |
| AC3 | A custom `@tool` participates in the tool loop. |
| AC4 | A structured agent returns the declared Pydantic type. |
| AC5 | Nested Pydantic results validate and retain their nested types. |
| AC6 | Text after tool calls is the returned final answer. |
| AC7 | A model alias changes providers through YAML alone. |
| AC8 | Model IDs containing slashes pass through unchanged. |
| AC9 | Concurrent calls on one agent keep histories and counters separate. |
| AC10 | JSON embedded in plain text is not accepted as structured output. |
| AC11 | Invalid tool calls are repaired without guessed execution or partial side effects. |

The [traceability matrix](traceability.md) links each criterion to tickets and
automated tests. [Architecture decisions](decisions.md) explain why the
contract is shaped this way. The [release chapter](06-quality-security-release.md)
lists the remaining checks before a PyPI publication decision.
