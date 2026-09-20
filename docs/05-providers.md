# Provider adapters

Every adapter exposes capabilities, `async complete(ModelRequest)`, and
`async close()`. It returns a normalized `ModelResponse` containing text,
tool calls, structured output when requested, finish reason, usage, and
optional debug data. Malformed tool arguments retain their raw form so the
shared preflight layer can return useful feedback. Adapters must not leak
SDK-specific objects into the core API or put a native structured result in
the text field.

`ProviderRequestError` records an optional HTTP status and retryability.
HTTP 429 and selected 5xx responses are transient; typical 4xx failures are
not. Three capability flags describe tool calling, guaranteed native
structured output, and parallel tool calls. Local endpoints may override
these flags explicitly in YAML.

## Supported providers

| Type | Transport and authentication | Notes |
| --- | --- | --- |
| `openai_compatible` | `httpx.AsyncClient`, optional API key | OpenAI-style `chat/completions`; suitable for llama-server, vLLM, SGLang, and similar endpoints. |
| `openrouter` | Shared OpenAI-compatible transport, Bearer key | Defaults to `https://openrouter.ai/api/v1`; optional `HTTP-Referer` and `X-OpenRouter-Title` headers. Model IDs remain opaque. |
| `azure_openai` | Shared HTTP transport, `api-key` or explicit Bearer header | Model ID is the deployment in the URL; `api-version` is required. |
| `azure_foundry` | Shared HTTP transport, `api-key` or explicit Bearer header | Uses the configured endpoint and an optional API version. |
| `vertex_ai` | Optional `google-genai` SDK, ADC/service account | Maps message parts, function calls, generation options, native schema, and token usage; inline API keys and custom auth headers are rejected. |

OpenAI-compatible responses normalize provider usage and tool-call IDs.
OpenRouter additionally preserves reported cost when present; absent usage
values remain `None`, not zero. Native structured output is not guaranteed
for arbitrary OpenRouter or local models by default.

The Azure adapters need only core `httpx`; the `azure` extra exists as a
stable, intentionally empty install target. Vertex AI requires
`pip install "moiryx[google]"`. The core package does not install Google SDK
unless requested.

One `Agent` reuses its provider client across steps and calls. Separate agent
instances do not share a connection pool or run history. In a long-lived
process, use `await agent.aclose()` or `async with Agent(...)` to close the
client. The basic one-off call does not require a context manager.

Adapter tests use mock HTTP transports or injected SDK clients. Live tests
are opt-in through the `integration` marker and explicit environment
variables. Local endpoint smoke tests require
`MOIRYX_OPENAI_COMPATIBLE_LIVE_URL` and
`MOIRYX_OPENAI_COMPATIBLE_LIVE_MODEL`; an optional key uses
`MOIRYX_OPENAI_COMPATIBLE_LIVE_API_KEY`.
