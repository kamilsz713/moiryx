# Architecture

```text
Application code ── await agent(prompt) ──> Agent
                                        ├── Markdown -> AgentSpec
                                        ├── YAML -> model/provider registry
                                        └── selected tools/output model
                                                   │
                                                   ▼
                                Runtime + per-call RunContext
                                  ├── provider retry and limits
                                  ├── whole-batch tool preflight
                                  ├── tool execution and repair
                                  ├── structured result validation
                                  └── events and trace
                                                   │
                                                   ▼
                                      ProviderAdapter -> API/SDK
```

`Agent` resolves configuration, model, provider, tools, and output schema at
construction. It holds no per-run messages. Each call creates its own
`RunContext`, so one agent instance can serve concurrent calls without mixing
histories. Call `await agent.aclose()` or use `async with Agent(...)` to release
its provider client in a long-lived process.

The provider boundary takes a normalized `ModelRequest` and returns a
`ModelResponse`. Adapters retain malformed raw tool arguments for the shared
repair layer but do not expose SDK objects to the runtime. The core does not
branch on provider names, and tools do not import provider adapters.

## One run

1. Start an isolated context with system and user messages.
2. Request a model response; retries do not consume extra agent steps.
3. Preflight every tool call before executing any call in the batch.
4. If the batch is invalid, execute none of it and return bounded repair
   feedback. Otherwise, execute calls sequentially.
5. Stop on final text or a validated structured result. Missing content,
   exhausted repair budgets, and step limits raise explicit errors.

Events observe this flow but never control it. Logging and optional JSONL
traces redact configured secrets before output.

## Repository layout

- `src/moiryx/agent.py`, `agent_spec.py`, `config.py`: user entry point and
  configuration loading.
- `runtime.py`, `messages.py`, `models.py`: provider-neutral execution.
- `tools/`, `output/`, `providers/`: isolated subsystems.
- `tests/`: deterministic unit, adapter, acceptance, and opt-in live tests.
