# v0.1 risks

Probability and impact use Low / Medium / High. The linked epic owns a risk
until a person is assigned. Close a risk only with a relevant test, decision,
or dogfooding result.

| ID | Risk | Probability | Impact | Mitigation / tickets |
| --- | --- | --- | --- | --- |
| R-01 | OpenAI-compatible endpoints support different subsets of tool calling | High | High | Minimal requests, capability overrides, contract tests; MRYX-601–603. |
| R-02 | Provider SDK types leak into the core | Medium | High | Normalized provider protocol and boundary tests; MRYX-401, 901, 1001. |
| R-03 | Tool repair causes an unintended mutation | Medium | High | Conservative repair, full-batch preflight, side-effect tests; MRYX-305–307. |
| R-04 | A structured result appears valid but violates its model | Medium | High | Final tool or native schema plus Pydantic validation; MRYX-501–504. |
| R-05 | Concurrent runs mix messages or traces | Medium | High | Per-call `RunContext` and run-ID trace paths; MRYX-406, 1102. |
| R-06 | Credentials appear in logs or raw responses | Medium | High | Central redaction and opt-in raw diagnostics; MRYX-1103. |
| R-07 | `shell` behavior differs across platforms | High | Medium | Windows/Linux tests for process cleanup and command semantics; MRYX-706. |
| R-08 | Provider extras make the core install heavy or incompatible | Medium | Medium | Isolated extras and clean-install CI; MRYX-903, 1002, 1105. |
| R-09 | Cached configuration makes tests or environment changes order-dependent | Medium | Medium | Explicit reset and isolated fixtures; MRYX-101. |
| R-10 | Traces or tool output grow without bound | Medium | Medium | Output limits, opt-in traces, raw data off by default; MRYX-304, 1102. |
| R-11 | The `moiryx` distribution name is unavailable on PyPI | Medium | Medium | Confirm before publication; keep the Python import name; MRYX-1107. |
| R-12 | Scope creep delays a stable core | High | Medium | Enforce non-goals and milestone gates; ADR-002, MRYX-1106. |

Short, focused spikes are appropriate for uncertain Azure Foundry endpoint
variants, Vertex AI function-call/schema mapping, and cross-platform shell
behavior. A spike does not change the public contract; a required change gets
an ADR and specification update first.
