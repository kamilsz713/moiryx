# Using Moiryx

The [README](../README.md) shows the smallest working agent. This guide covers
the options you are likely to need after that first call.

## Configuration and agent files

Moiryx reads `./moiryx.yaml` from the current working directory, or the file
named by `MOIRYX_CONFIG`. It does not search parent directories or merge files.
Keep credentials in environment variables; `${NAME}` in YAML is replaced with
the corresponding value when configuration loads.

```yaml
providers:
  local:
    type: openai_compatible
    base_url: http://127.0.0.1:8080/v1

models:
  chat:
    provider: local
    model: local-model
    generation:
      temperature: 0.2

runtime:
  default_max_steps: 20
  workspace_root: .
  allow_paths_outside_workspace: false
```

`providers` names connections; `models` names aliases used by agents. Model
IDs are passed through unchanged, including IDs with slashes. Generation
settings merge from runtime defaults, then the model, then the agent.

An agent is a Markdown file with YAML frontmatter. Only `model` is required:

```markdown
---
model: chat
tools: [read_file, grep]
max_steps: 12
---
Answer the user's question using the selected tools when helpful.
```

`Agent("agents/chat.md")` validates the config, model alias, selected tools,
and optional output model before sending a request. Each call is independent;
there is no implicit conversation memory. Use `async with Agent(...)` or
`await agent.aclose()` in long-lived processes to close provider connections.

## Tools

Built-in tools are opt-in through the agent's `tools` list:

| Task | Tools |
| --- | --- |
| Read and search | `read_file`, `list_files`, `glob_files`, `grep` |
| Write | `write_file`, `edit_file` |
| Run a process | `shell` |

File tools stay under `runtime.workspace_root` by default, including symlink
checks. `shell` is **not a sandbox**; enable it only for agents you trust.

For a custom tool, decorate a typed function, list its module in
`tool_modules` in `moiryx.yaml`, and add its function name to the agent's
`tools` list. See [the README example](../README.md#custom-tools).
Moiryx validates all calls in a model response before running any of them.

## Structured output

Set `output: module:ClassName` in the agent frontmatter, where the class is a
Pydantic `BaseModel`. The call then returns an instance of that class rather
than text. The provider must support tool calling or guaranteed native
structured output; ordinary JSON in a text answer is not accepted. See the
[README example](../README.md#structured-output).

## Retries and diagnostics

`runtime.provider_retry_attempts` bounds retries for transient transport
errors and rate limits. `runtime.structured_output_retries` and
`runtime.tool_call_repair_attempts` bound correction loops separately.
Configuration or authentication errors are not retried as transient failures.

Set `logging.trace_dir` to write one `events.jsonl` file per invocation. No
trace files are written by default. Raw provider responses are disabled unless
`logging.include_raw_response` is true; configured secrets and sensitive
fields are redacted either way. Treat traces as application data and protect
the directory accordingly.
