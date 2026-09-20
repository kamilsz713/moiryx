# Changelog

Notable changes are recorded here. Versions follow PEP 440; `0.1.0a1` is the
first alpha.

## 0.1.0a1

### Added

- Markdown agent definitions, YAML model aliases, and the `Agent` and `@tool`
  public API.
- Text-agent runtime with tool validation, conservative repair of malformed
  calls, and separate retry budgets.
- Pydantic structured results, including nested models, through a synthetic
  final tool or native JSON schema where the provider supports it.
- OpenAI-compatible, OpenRouter, Azure OpenAI, Azure Foundry, and Vertex AI
  adapters.
- Workspace-scoped file tools and an explicitly enabled `shell` tool.
- Run events, optional JSONL traces, and centralized secret redaction.
- Deterministic AC1–AC11 acceptance tests, examples, and a CI matrix.

### Alpha limitations

- No streaming, sessions, multimodal input, or automatic model fallback.
- `shell` is not a sandbox; use it only in trusted environments.
- Function calling and JSON-schema behavior of local models depend on the
  model and its chat template.

See the [alpha release notes](docs/release-notes-alpha.md) for verification
details and limitations.
