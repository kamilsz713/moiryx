# Moiryx

Moiryx lets you define an agent in Markdown, select its model in YAML, and call
it like an async Python object. You can move the same agent from a local
`llama-server` to OpenRouter, Azure, or Vertex AI without changing Python code.

This project is an alpha. Its deliberately small user-facing API consists of
`Agent`, `@tool`, and `moiryx.yaml`.

## Installation

Install the alpha from PyPI:

```bash
python -m pip install moiryx==0.1.0a1
```

For development from this checkout:

```bash
python -m pip install -e .
```

Vertex AI requires the optional Google Gen AI SDK. For a PyPI installation:

```bash
python -m pip install "moiryx[google]==0.1.0a1"
```

From this checkout:

```bash
python -m pip install -e ".[google]"
```

## Your first agent with a local llama-server

Start an OpenAI-compatible endpoint and create `moiryx.yaml`:

```yaml
providers:
  local:
    type: openai_compatible
    base_url: http://127.0.0.1:8080/v1

models:
  local_chat:
    provider: local
    model: local-model
```

Save the agent as `agents/chat.md`:

```markdown
---
model: local_chat
---
Answer directly and say when you are uncertain.
```

Call it from Python:

```python
import asyncio

from moiryx import Agent


async def main() -> None:
    agent = Agent("agents/chat.md")
    answer = await agent("What is the difference between a process and a thread?")
    print(answer)


asyncio.run(main())
```

For a long-lived application, call `await agent.aclose()` when you are done, or
use `async with Agent(...)`. This releases the provider's HTTP connections. A
one-off script can simply exit.

## Built-in tools

Tools are opt-in. Add only the ones an agent needs to its frontmatter:

```markdown
---
model: local_chat
tools: [read_file, list_files, grep]
---
Inspect files in the workspace and cite the paths you used.
```

Available tools are `read_file`, `list_files`, `glob_files`, `grep`,
`write_file`, `edit_file`, and `shell`. File operations stay within
`runtime.workspace_root` by default.

> `shell` is not a security sandbox. Enable it only for agents and workspaces
> you trust.

## Custom tools

```python
from moiryx import tool


@tool
def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())
```

Import the module through the configuration, then select the tool in the
agent definition:

```yaml
tool_modules: [my_tools]
```

```markdown
---
model: local_chat
tools: [word_count]
---
Use the tool to count words accurately.
```

## Structured output

Declare the result with an ordinary Pydantic model:

```python
from pydantic import BaseModel, Field


class ReviewResult(BaseModel):
    accepted: bool
    score: float = Field(ge=0, le=1)
    findings: list[str]
```

Reference it as `module:Class` in the agent:

```markdown
---
model: local_chat
output: review_models:ReviewResult
---
Review the change and return a result matching the schema.
```

`await agent(...)` returns a `ReviewResult` instance. JSON embedded in plain
text does not count as a structured result.

## Switching providers in YAML

Keep the Python code and agent file; change the model alias configuration:

```yaml
providers:
  router:
    type: openrouter
    api_key: ${OPENROUTER_API_KEY}
    headers:
      HTTP-Referer: https://example.invalid
      X-OpenRouter-Title: Moiryx example

models:
  local_chat:
    provider: router
    model: provider/model-id
```

Supported provider types are `openai_compatible` (including llama-server,
vLLM, and SGLang), `openrouter`, `azure_openai`, `azure_foundry`, and
`vertex_ai` (using Application Default Credentials or a service account).

## Logging and traces

```yaml
logging:
  level: INFO
  trace_dir: .moiryx/runs
  include_raw_response: false
```

Each run has its own ID and, when tracing is enabled, an
`.moiryx/runs/<run-id>/events.jsonl` file. Raw provider responses are off by
default. If enabled, configured secrets and sensitive fields are still
redacted.

## Examples

See [`examples/`](examples/) for runnable definitions, the
[usage guide](docs/usage.md) for configuration and tools, and the
[provider guide](docs/providers.md) for connection examples.
