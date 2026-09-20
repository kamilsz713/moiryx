# Quality, security, and release

## Errors and diagnostics

Public errors derive from `MoiryxError`. Configuration, agent definitions,
unknown models or tools, provider capabilities and requests, malformed tool
calls, structured output, protocol violations, and step limits have distinct
exception types. Error messages include useful run and model context without
printing credentials.

The `moiryx.run` logger emits run boundaries at INFO, request and successful
tool metadata at DEBUG, retries and repairs at WARNING, and terminal failures
at ERROR. Set `logging.trace_dir` to write a separate
`<run-id>/events.jsonl` file per invocation. Raw provider responses require
`logging.include_raw_response: true` and are still redacted. No trace files
are created by default.

Redaction handles `SecretStr`, sensitive field names, and configured secret
values embedded in text. The runtime never logs a failed preflight call as a
completed tool execution. Keep credentials in environment variables and do
not commit local configuration files.

## Security boundaries

- File tools resolve paths beneath `workspace_root` unless explicitly
  configured otherwise. This is a path policy, not a hostile-user sandbox.
- Whole-batch preflight prevents partial side effects from an invalid batch.
- Tool names and missing arguments are never guessed.
- Built-ins are exposed only when selected by an agent.
- `grep` invokes `rg` without a shell. The explicit `shell` tool *does* use
  the system shell and can reach resources outside the workspace; its timeout
  and output bounds do not make it safe for untrusted use.

## Verification

`python scripts/check.py` runs offline tests, Ruff, and mypy for both the
host platform and Linux. `python -m pytest -m acceptance -q` runs the
AC1–AC11 scenarios. CI checks Python 3.11 and 3.12, builds wheel and sdist,
audits release archives, and smoke-tests an installed wheel. Live provider
tests are opt-in and are not required in CI.

High-risk regression cases include whole-batch validation before writes,
bounded tool and structured-output repair, nested Pydantic results, rejection
of plain JSON text as structured output, concurrent run isolation, model IDs
with slashes, process cancellation, and secret redaction.

## Alpha release gate

The `publish.yml` workflow builds and checks wheel and sdist after a GitHub
release is published. It rejects a tag that does not match the version in
`pyproject.toml`, then publishes through PyPI Trusted Publishing. Only the
publish job receives OIDC permission. It uses the GitHub `pypi` environment
as its manual approval gate; create that environment with a required reviewer
before publishing a release.

For the first release, create a pending Trusted Publisher in PyPI with these
exact fields: project `moiryx`, GitHub owner `kamilsz713`, repository `moiryx`,
workflow `publish.yml`, and environment `pypi`. A pending publisher does not
reserve the project name. After the environment and publisher are configured,
publish the GitHub release with tag `v0.1.0a1` from the verified `main` commit,
mark it as a pre-release, approve the `pypi` environment deployment, and
verify the PyPI project page and a clean installation. Do not create the
release before both account-side settings are ready. No PyPI API token is
needed or stored in GitHub.

API stability beyond this alpha is not promised.
