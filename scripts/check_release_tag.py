"""Require the GitHub release tag to match the package version."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def check_release_tag(tag: str) -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    expected = f"v{project['project']['version']}"
    if tag != expected:
        raise ValueError(f"Release tag {tag!r} must be {expected!r}")


if __name__ == "__main__":
    check_release_tag(os.environ["GITHUB_REF_NAME"])
