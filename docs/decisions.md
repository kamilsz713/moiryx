# Architecture decisions

These decisions are accepted for v0.1. A change requires an explicit
superseding decision and updates to the specification and tests.

## ADR-001: Small public API

`Agent(agent_file)` and `@tool` are the user entry points. Model selection,
tools, and output schema stay out of orchestration code. No default `run()`,
`invoke()`, or builder API is planned.

## ADR-002: Orchestration stays in Python

Moiryx does not provide a graph, workflow, or chain DSL. Application functions
own branching, looping, and concurrency so control flow remains inspectable.

## ADR-003: Pydantic defines structured results

A successful structured run returns the declared `BaseModel` instance. It
uses the reserved final tool or guaranteed native structured output. Parsing
JSON out of prose is not a fallback.

## ADR-004: Preflight the whole tool batch

Resolve, parse, and validate every call before executing any call. One invalid
call blocks the entire batch, preventing partial side effects.

## ADR-005: Conservative repair only

Repair unambiguous syntax and transport mistakes; never fuzzy-match a tool or
invent arguments. A suggested name goes back to the model for an explicit new
call.

## ADR-006: Per-call run state

Every `await agent(prompt)` has its own `RunContext`. Agents have no implicit
conversation memory, and concurrent calls cannot share message history.

## ADR-007: Sequential tools in v0.1

A valid batch executes in model order. This makes mutations and diagnostics
predictable even if a provider reports parallel tool-call capability.

## ADR-008: Moiryx naming

The package, import, examples, and configuration use `moiryx`. No legacy
aliases are provided before the first public release.
