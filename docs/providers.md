# Connecting providers

Choose a provider in `moiryx.yaml`, then point a model alias at it. The agent
file and Python code stay the same when the alias moves to another provider.
Use environment variables for credentials; do not put literal keys in YAML.

## Local llama-server or llama-swap

Both can expose an OpenAI-compatible chat endpoint. Replace `local-model`
with the model ID served by your endpoint:

```yaml
providers:
  local:
    type: openai_compatible
    base_url: http://127.0.0.1:8080/v1

models:
  chat:
    provider: local
    model: local-model
```

If an endpoint supports tool calling or native structured output but does
not advertise it reliably, set the corresponding boolean in
`providers.local.capabilities`. Only enable a capability the endpoint and
model actually support; local behavior also depends on the chat template.

## OpenRouter

```yaml
providers:
  router:
    type: openrouter
    api_key: ${OPENROUTER_API_KEY}

models:
  chat:
    provider: router
    model: provider/model-id
```

The default endpoint is `https://openrouter.ai/api/v1`. Optional `headers`
can include `HTTP-Referer` and `X-OpenRouter-Title`. Model IDs are not
rewritten. Tool and structured-output support varies by model.

## Azure OpenAI and Azure Foundry

Azure OpenAI needs the resource endpoint and API version. Its model ID is the
deployment name:

```yaml
providers:
  azure:
    type: azure_openai
    endpoint: https://your-resource.openai.azure.com/
    api_version: 2025-04-01-preview
    api_key: ${AZURE_OPENAI_API_KEY}

models:
  chat:
    provider: azure
    model: your-deployment
```

For Azure Foundry, use `type: azure_foundry` and its model endpoint; the
`api_version` field is optional. Both adapters also support an explicitly
configured Bearer authorization header instead of `api_key`. Keep either
credential in the environment, not the repository.

## Vertex AI

Install the optional dependency with `python -m pip install "moiryx[google]"`.
Authenticate through Google Application Default Credentials or set
`GOOGLE_APPLICATION_CREDENTIALS` to a service-account file outside the repo.

```yaml
providers:
  vertex:
    type: vertex_ai
    project: your-gcp-project
    location: us-central1

models:
  chat:
    provider: vertex
    model: your-model-id
```

The Vertex adapter does not accept an inline API key or custom authentication
headers. See the [usage guide](usage.md) for agent and tool configuration.
