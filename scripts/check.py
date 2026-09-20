"""Run the local quality gates with one cross-platform command."""

from __future__ import annotations

import subprocess
import sys

COMMANDS = (
    (sys.executable, "-m", "pytest", "-q"),
    (sys.executable, "-m", "ruff", "check", "src", "tests", "scripts", "examples"),
    (
        sys.executable,
        "-m",
        "ruff",
        "format",
        "--check",
        "src",
        "tests",
        "scripts",
        "examples",
    ),
    (sys.executable, "-m", "mypy"),
    (sys.executable, "-m", "mypy", "--platform", "linux"),
)


def main() -> int:
    """Run each gate in order and return the first failing exit code."""
    for command in COMMANDS:
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
