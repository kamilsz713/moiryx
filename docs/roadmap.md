# v0.1 roadmap

Milestones move from a deterministic core to provider adapters and an alpha
release. Ticket IDs link to the [backlog](tickets/README.md). Sizes describe
relative effort, not calendar commitments.

| Milestone | Tickets | Outcome and gate |
| --- | --- | --- |
| M0: foundation | MRYX-001–004 | Package layout, canonical names, shared models and errors; local tests, lint, and typing run. |
| M1: configuration | MRYX-101–106, 201–203 | `Agent("agent.md")` validates config, aliases, tools, output model, and capabilities before a model request. |
| M2: tools | MRYX-301–307 | Typed sync/async tools, schemas, timeout, whole-batch preflight, and conservative repair; invalid batches have no side effects. |
| M3: text runtime | MRYX-401–406 | Deterministic tool loop, retry, limits, cancellation, and isolated concurrent calls; AC1–3, AC6, AC9, and text AC11 pass. |
| M4: structured output | MRYX-501–504 | Pydantic results through a final tool or guaranteed native schema; AC4, AC5, AC10 pass without JSON-from-text fallback. |
| M5: local provider and built-ins | MRYX-601–603, 701–706 | OpenAI-compatible adapter, mock/live smoke, workspace path policy, and tested file/shell tools. |
| M6: provider matrix | MRYX-801–802, 901–903, 1001–1002 | OpenRouter, Azure, and Vertex AI adapters with credential-free mock tests and optional dependencies. |
| M7: observability and alpha | MRYX-1101–1107 | Redacted events/traces, docs, dogfooding, acceptance suite, clean-install artifacts, and an explicit publication decision. |

Contract tests precede live provider integration. Adapters must not change
the public API or duplicate runtime behavior. Repair and structured-output
safety are features, not post-release polish. A dependent ticket should wait
for its contract dependency.

The critical path is configuration → eager `Agent` → tools/preflight →
provider protocol → text loop → structured output → local adapter → built-ins
and dogfooding → packaging. OpenRouter, Azure, and Vertex AI can develop in
parallel once the provider boundary is stable.

Streaming, sessions, multimodal input, permission prompts, MCP, remote tools,
fallback routing, context policies, replay, OpenTelemetry, caching, parallel
tool execution, generated code, and container sandboxing remain outside v0.1.
