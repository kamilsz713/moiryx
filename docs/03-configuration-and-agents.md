# Configuration and agent definitions

Moiryx reads the path in `MOIRYX_CONFIG` when set, otherwise `./moiryx.yaml`
from the current working directory. It does not merge files or search parent
directories. Call `reset_config_cache()` only when deliberately reloading a
configuration in the same process.

```yaml
providers:
  local:
    type: openai_compatible
    base_url: http://127.0.0.1:8080/v1

models:
  reviewer:
    provider: local
    model: local-model

runtime:
  default_max_steps: 20
  provider_retry_attempts: 3
  structured_output_retries: 2
  tool_call_repair_attempts: 2
  tool_timeout_seconds: 60
  workspace_root: .
  allow_paths_outside_workspace: false
  max_tool_output_chars: 50000

logging:
  level: INFO
  trace_dir: .moiryx/runs
  include_raw_response: false
```

`providers` keys name connections; `models` keys name logical model aliases.
Model IDs are opaque strings, including IDs with slashes. String values may
contain `${ENV_VAR}` references; missing variables fail configuration loading.
Keep secrets in environment variables rather than committed YAML.

Generation options merge in this order: runtime defaults, model settings,
then agent overrides. The common options are `temperature`, `max_tokens`,
`top_p`, and `seed`. Unknown options are rejected. `tool_modules` explicitly
lists modules to import for custom tools; there is no filesystem scan.

An agent file contains YAML frontmatter followed by Markdown system
instructions:

```markdown
---
name: reviewer
model: reviewer
tools: [read_file, grep]
output: my_project.schemas.review:ReviewOutput
max_steps: 20
generation:
  temperature: 0.2
---
Review the code and report specific findings.
```

Only `model` is required. `name` defaults to the file stem; `tools` defaults
to an empty list; `output` is an import path to a `BaseModel` subclass;
`max_steps` defaults to `runtime.default_max_steps`. The constructor catches
invalid files, aliases, tool names, output models, options, and unsupported
provider capabilities before the first request.

The `moiryx.run` logger emits run boundaries at INFO, model and successful
tool steps at DEBUG, retries and repairs at WARNING, and failed runs at ERROR.
Setting `logging.trace_dir` writes one `events.jsonl` per run. Raw responses
are disabled by default and remain subject to central redaction when enabled.
