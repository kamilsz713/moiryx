"""Canonical workspace path checks shared by built-in tools."""

from __future__ import annotations

from pathlib import Path

from moiryx.errors import BuiltinToolError


class WorkspacePathError(BuiltinToolError):
    """A requested path is invalid or outside the configured workspace."""


class WorkspacePathGuard:
    """Resolve paths and enforce containment beneath one canonical root."""

    __slots__ = ("_allow_outside", "_root")

    def __init__(self, root: str | Path, *, allow_outside: bool = False) -> None:
        try:
            self._root = Path(root).expanduser().resolve(strict=False)
        except (OSError, RuntimeError, ValueError) as error:
            raise WorkspacePathError(
                f"Could not resolve workspace root ({type(error).__name__})"
            ) from error
        self._allow_outside = allow_outside

    @property
    def root(self) -> Path:
        return self._root

    @property
    def allow_outside(self) -> bool:
        return self._allow_outside

    def resolve(self, path: str | Path, *, must_exist: bool = False) -> Path:
        """Return a canonical path after applying the workspace policy."""
        raw = Path(path).expanduser()
        candidate = raw if raw.is_absolute() else self._root / raw
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError, ValueError) as error:
            raise WorkspacePathError(
                f"Could not resolve path '{path}' ({type(error).__name__})"
            ) from error

        if not self._allow_outside and not resolved.is_relative_to(self._root):
            raise WorkspacePathError("Path is outside the configured workspace")
        if must_exist and not resolved.exists():
            raise WorkspacePathError(f"Path does not exist: {path}")
        return resolved

    def display(self, path: Path) -> str:
        """Render an already resolved path without assuming it is inside root."""
        try:
            relative = path.relative_to(self._root)
        except ValueError:
            return str(path)
        rendered = relative.as_posix()
        return rendered if rendered else "."


__all__ = ["WorkspacePathError", "WorkspacePathGuard"]
