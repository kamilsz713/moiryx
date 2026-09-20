# 0.1.0a1 — pre-publication status

Moiryx has not been published to PyPI. These notes record the first alpha's
verification and remaining release work, not a publication announcement.

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

## Remaining

- Create the GitHub `pypi` environment with a required reviewer and configure
  the matching pending PyPI Trusted Publisher. The `moiryx` project page is
  currently absent, but the name is not reserved until the first publication.
- Publish the `v0.1.0a1` GitHub pre-release, approve the environment, and verify
  the uploaded distributions and clean installation from PyPI.

`shell` is not a sandbox. Local function-calling and JSON-schema behavior
depends on the model and chat template; one successful smoke test is not a
guarantee for other models.
