# Vision and public contract

Moiryx is a small, configuration-driven Python runtime for LLM agents. It
handles provider requests, tool calls, validation, retries, and typed results;
application orchestration remains ordinary Python.

## Public API

```python
from moiryx import Agent, tool

reviewer = Agent("agents/reviewer.md")
review = await reviewer("Review src/cache.py")
```

The v0.1 contract is intentionally narrow:

- `Agent` takes an agent-file path; `await agent(prompt)` starts an isolated run.
- An agent without `output` returns final text. An agent with `output` returns
  an instance of the declared Pydantic model.
- `@tool` registers an ordinary Python function under its function name.
- Markdown contains instructions, YAML selects the provider and model, and
  Python controls multi-agent orchestration.
- No default result wrapper, `run()` method, constructor model override, or
  JSON-from-prose fallback is part of the public API.

## Scope

The alpha includes text and structured agent loops, custom and workspace
tools, OpenAI-compatible/OpenRouter/Azure/Vertex AI adapters, bounded retries,
run events, optional JSONL traces, and deterministic offline tests.

It does not include a workflow DSL, persistent memory, RAG framework, vector
store, HTTP server, GUI, distributed workers, streaming API, automatic context
compression, MCP, policy engine, or automatic model fallback. Those should be
added only when real use cases justify shared abstractions.

Success means a text agent, a tool-using agent, and a nested structured-result
agent work without special cases; the same agent can switch providers through
YAML; invalid tool calls cannot cause guessed side effects; concurrent runs do
not share history; and errors and traces explain what happened.
