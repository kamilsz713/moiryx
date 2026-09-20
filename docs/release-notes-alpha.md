# 0.1.0a1 — alpha release notes

These notes record the first alpha's verification and limitations. The
published package, when available, is at
<https://pypi.org/project/moiryx/0.1.0a1/>.

## Verified

- AC1–AC11, the offline test suite, Ruff, and mypy passed locally.
- Wheel and sdist include MIT metadata and the changelog; artifact auditing
  found no local credentials. A wheel was installed and smoke-tested in a
  clean Python 3.12 environment.
- GitHub CI passed on Python 3.11 and 3.12, including the artifact job.
- A small text smoke test used the same agent on local llama-swap (Bonsai)
  and OpenRouter (`inclusionai/ling-3.0-flash-vl:free`). Local function-calling
  and JSON-schema examples were also exercised. Live-test configuration stays
  private and is not part of the repository.

`shell` is not a sandbox. Local function-calling and JSON-schema behavior
depends on the model and chat template; one successful smoke test is not a
guarantee for other models.
