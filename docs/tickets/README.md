# v0.1 implementation backlog

This is the compact record of the original implementation tickets. Ticket
sizes are relative (`S`, `M`, `L`), not dates. Every ticket below is a `Must`
for the first alpha. All are `Done` except MRYX-1107, which remains in
progress until the PyPI name and publication decision are resolved.

The shared Definition of Done is: observable acceptance behavior, a relevant
failure/edge-case test, passing pytest/Ruff/type checks, no leaked secrets or
unintended public API, and current docs when the contract changes. Offline
tests are the default; live provider checks are explicit opt-ins.

## E0 — foundation

| Ticket | Outcome |
| --- | --- |
| MRYX-001 | Create the `src/moiryx` package, `pyproject.toml`, and test layout. |
| MRYX-002 | Configure pytest, Ruff, and strict typing for local and CI runs. |
| MRYX-003 | Define specific, contextual errors under `MoiryxError`. |
| MRYX-004 | Define provider-neutral messages, requests, responses, and tool models. |

## E1 — configuration and registries

| Ticket | Outcome |
| --- | --- |
| MRYX-101 | Discover `MOIRYX_CONFIG` or `./moiryx.yaml`; fail clearly if missing. |
| MRYX-102 | Interpolate `${NAME}` recursively and reject missing variables without leaking values. |
| MRYX-103 | Validate provider, model, runtime, and logging sections; reject unknown fields. |
| MRYX-104 | Resolve model aliases while preserving opaque model IDs. |
| MRYX-105 | Merge generation options in runtime → model → agent order. |
| MRYX-106 | Instantiate and close provider adapters through an explicit registry. |

## E2 — agent definitions

| Ticket | Outcome |
| --- | --- |
| MRYX-201 | Parse Markdown with YAML frontmatter into a validated `AgentSpec`. |
| MRYX-202 | Import a declared Pydantic output model and reject invalid references. |
| MRYX-203 | Resolve config, model, tools, output, and capabilities eagerly in `Agent`. |

## E3 — custom tools and repair

| Ticket | Outcome |
| --- | --- |
| MRYX-301 | Register ordinary Python callables through `@tool`; reject duplicates. |
| MRYX-302 | Derive input schemas and descriptions from type hints and docstrings. |
| MRYX-303 | Execute validated sync/async tools with timeout and typed failures. |
| MRYX-304 | Serialize results with an explicit output limit and truncation marker. |
| MRYX-305 | Preflight every call before any call in a batch executes. |
| MRYX-306 | Repair only unambiguous argument transport/syntax errors. |
| MRYX-307 | Return bounded repair feedback and detect repeated invalid calls. |

## E4 — provider protocol and text runtime

| Ticket | Outcome |
| --- | --- |
| MRYX-401 | Define a normalized async provider protocol and message mapping. |
| MRYX-402 | Provide a scripted fake adapter for deterministic offline tests. |
| MRYX-403 | Implement the text agent's model/tool/final-response loop. |
| MRYX-404 | Execute valid multiple tool calls sequentially in model order. |
| MRYX-405 | Classify transient provider errors and use bounded backoff. |
| MRYX-406 | Isolate concurrent runs and propagate cancellation. |

## E5 — structured output

| Ticket | Outcome |
| --- | --- |
| MRYX-501 | Generate the reserved synthetic final tool from a Pydantic model. |
| MRYX-502 | Return the exact validated Pydantic type, including nested fields. |
| MRYX-503 | Reject mixed/duplicate final calls and plain JSON-text fallback. |
| MRYX-504 | Route by guaranteed capabilities or fail before a run. |

## E6 — OpenAI-compatible adapter

| Ticket | Outcome |
| --- | --- |
| MRYX-601 | Send minimal async chat-completion requests through `httpx`. |
| MRYX-602 | Normalize text, calls, malformed arguments, usage, and errors. |
| MRYX-603 | Cover mapping with mock transport and an opt-in local smoke test. |

## E7 — built-in tools

| Ticket | Outcome |
| --- | --- |
| MRYX-701 | Resolve workspace paths and block traversal through symlinks. |
| MRYX-702 | Add UTF-8 `read_file` with inclusive line ranges. |
| MRYX-703 | Add bounded `list_files`, `glob_files`, and `grep`. |
| MRYX-704 | Add atomic `write_file`. |
| MRYX-705 | Add atomic, exactly-one-match `edit_file`. |
| MRYX-706 | Add explicit `shell` with timeout, output bounds, and process cleanup; document that it is not a sandbox. |

## E8 — OpenRouter

| Ticket | Outcome |
| --- | --- |
| MRYX-801 | Add OpenRouter defaults and Bearer authentication without duplicating the OpenAI-compatible adapter. |
| MRYX-802 | Preserve model IDs, usage, and cost, with mocked adapter tests. |

## E9 — Azure OpenAI and Foundry

| Ticket | Outcome |
| --- | --- |
| MRYX-901 | Map Azure OpenAI deployment routes, API version, and authentication. |
| MRYX-902 | Map Azure Foundry endpoint and optional API-version semantics. |
| MRYX-903 | Keep unnecessary Azure SDKs out of core; test both adapters offline. |

## E10 — Vertex AI

| Ticket | Outcome |
| --- | --- |
| MRYX-1001 | Add async Vertex AI mapping for messages, functions, schema, and usage with ADC/service-account auth. |
| MRYX-1002 | Add the Google extra and credential-free SDK mock matrix. |

## E11 — observability and alpha

| Ticket | Outcome |
| --- | --- |
| MRYX-1101 | Emit structured logging and per-call `RunContext` events. |
| MRYX-1102 | Write optional, isolated JSONL traces. |
| MRYX-1103 | Centralize secret redaction for config and diagnostics. |
| MRYX-1104 | Publish a usable README and examples for text, tools, and structured results. |
| MRYX-1105 | Run Python 3.11/3.12 CI and build/audit clean-install artifacts. |
| MRYX-1106 | Dogfood the main user paths and pass AC1–AC11 without network. |
| MRYX-1107 (in progress) | Confirm the PyPI name, publication setup, and owner's release decision for `0.1.0a1`. |

The [acceptance matrix](../traceability.md) connects AC1–AC11 to concrete
tests. The [roadmap](../roadmap.md) records dependencies and milestones. A
new ticket should use the [template](TEMPLATE.md) and should not change the
public API or security contract without an ADR.
