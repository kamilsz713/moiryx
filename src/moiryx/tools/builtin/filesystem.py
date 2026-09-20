"""Workspace-scoped filesystem built-ins."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from moiryx.errors import BuiltinToolError
from moiryx.models import ToolDefinition
from moiryx.tools.builtin.workspace import WorkspacePathGuard

PositiveLine = Annotated[int, Field(ge=1)]
ResultLimit = Annotated[int, Field(ge=1, le=10_000)]


class _BuiltinInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ReadFileInput(_BuiltinInput):
    path: Annotated[str, Field(min_length=1, description="File path.")]
    start_line: Annotated[
        PositiveLine | None,
        Field(description="Optional first line, inclusive and one-based."),
    ] = None
    end_line: Annotated[
        PositiveLine | None,
        Field(description="Optional last line, inclusive and one-based."),
    ] = None


class _ListFilesInput(_BuiltinInput):
    path: Annotated[
        str,
        Field(min_length=1, description="Directory to list without recursion."),
    ] = "."
    max_results: Annotated[
        ResultLimit,
        Field(description="Maximum number of entries to return."),
    ] = 100


class _GlobFilesInput(_BuiltinInput):
    pattern: Annotated[
        str,
        Field(min_length=1, description="Relative glob pattern, including **."),
    ]
    path: Annotated[
        str,
        Field(min_length=1, description="Directory in which to evaluate the glob."),
    ] = "."
    max_results: Annotated[
        ResultLimit,
        Field(description="Maximum number of matching files to return."),
    ] = 100


class _GrepInput(_BuiltinInput):
    pattern: Annotated[
        str,
        Field(min_length=1, description="Regular expression to search for."),
    ]
    path: Annotated[
        str,
        Field(min_length=1, description="File or directory to search."),
    ] = "."
    glob: Annotated[
        str | None,
        Field(description="Optional file glob such as *.py."),
    ] = None
    max_results: Annotated[
        ResultLimit,
        Field(description="Maximum number of matching lines to return."),
    ] = 100


class _WriteFileInput(_BuiltinInput):
    path: Annotated[str, Field(min_length=1, description="Destination file path.")]
    content: Annotated[str, Field(description="Complete UTF-8 file contents.")]


class _EditFileInput(_BuiltinInput):
    path: Annotated[str, Field(min_length=1, description="UTF-8 file to edit.")]
    old_text: Annotated[
        str,
        Field(min_length=1, description="Text that must occur exactly once."),
    ]
    new_text: Annotated[str, Field(description="Replacement text.")]


def _read_utf8(path: Path, *, requested_path: str) -> str:
    if not path.is_file():
        raise BuiltinToolError(f"Path is not a regular file: {requested_path}")
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise BuiltinToolError(f"File is not valid UTF-8: {requested_path}") from error
    except OSError as error:
        raise BuiltinToolError(
            f"Could not read file '{requested_path}' ({type(error).__name__})"
        ) from error


def _read_file(
    guard: WorkspacePathGuard,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    resolved = guard.resolve(path, must_exist=True)
    text = _read_utf8(resolved, requested_path=path)
    if start_line is None and end_line is None:
        return text

    first = 1 if start_line is None else start_line
    lines = text.splitlines(keepends=True)
    last = len(lines) if end_line is None else end_line
    if first < 1 or last < 1 or first > last:
        raise BuiltinToolError(
            "Invalid line range: lines are one-based and start must not exceed end"
        )
    if first > len(lines) or last > len(lines):
        raise BuiltinToolError(f"Invalid line range: file has {len(lines)} line(s)")
    return "".join(lines[first - 1 : last])


def _result_lines(values: Iterable[str], *, max_results: int) -> str:
    collected: list[str] = []
    truncated = False
    for value in values:
        if len(collected) >= max_results:
            truncated = True
            break
        collected.append(value)
    if truncated:
        collected.append(f"...[TRUNCATED BY MOIRYX: more than {max_results} results]")
    return "\n".join(collected)


def _list_files(
    guard: WorkspacePathGuard,
    path: str = ".",
    max_results: int = 100,
) -> str:
    directory = guard.resolve(path, must_exist=True)
    if not directory.is_dir():
        raise BuiltinToolError(f"Path is not a directory: {path}")
    try:
        entries = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
        rendered: list[str] = []
        for entry in entries:
            resolved = guard.resolve(entry, must_exist=True)
            label = guard.display(resolved)
            rendered.append(f"{label}/" if resolved.is_dir() else label)
        return _result_lines(rendered, max_results=max_results)
    except BuiltinToolError:
        raise
    except OSError as error:
        raise BuiltinToolError(
            f"Could not list directory '{path}' ({type(error).__name__})"
        ) from error


def _validate_glob_pattern(pattern: str) -> None:
    parsed = Path(pattern)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise BuiltinToolError(
            "Glob pattern must be relative and cannot contain parent traversal"
        )


def _glob_files(
    guard: WorkspacePathGuard,
    pattern: str,
    path: str = ".",
    max_results: int = 100,
) -> str:
    _validate_glob_pattern(pattern)
    directory = guard.resolve(path, must_exist=True)
    if not directory.is_dir():
        raise BuiltinToolError(f"Path is not a directory: {path}")
    try:
        matches: list[str] = []
        for candidate in directory.glob(pattern):
            resolved = guard.resolve(candidate, must_exist=True)
            if resolved.is_file():
                matches.append(guard.display(resolved))
        matches.sort(key=str.casefold)
        return _result_lines(matches, max_results=max_results)
    except BuiltinToolError:
        raise
    except (OSError, ValueError) as error:
        raise BuiltinToolError(
            f"Could not evaluate glob pattern ({type(error).__name__})"
        ) from error


def _grep_with_rg(
    executable: str,
    pattern: str,
    target: Path,
    glob_pattern: str | None,
    max_results: int,
) -> str:
    if target.is_dir():
        cwd = target
        target_argument = "."
    else:
        cwd = target.parent
        target_argument = target.name
    arguments = [
        executable,
        "--line-number",
        "--with-filename",
        "--no-heading",
        "--color",
        "never",
    ]
    if glob_pattern is not None:
        arguments.extend(("--glob", glob_pattern))
    arguments.extend(("--", pattern, target_argument))
    try:
        completed = subprocess.run(
            arguments,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            check=False,
        )
    except OSError as error:
        raise BuiltinToolError(
            f"Could not run ripgrep ({type(error).__name__})"
        ) from error
    if completed.returncode == 1:
        return ""
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        suffix = f": {detail[0]}" if detail else ""
        raise BuiltinToolError(
            f"ripgrep failed with exit code {completed.returncode}{suffix}"
        )
    return _result_lines(completed.stdout.splitlines(), max_results=max_results)


def _python_grep_files(target: Path) -> Iterable[Path]:
    if target.is_file():
        yield target
        return
    yield from sorted(
        (path for path in target.rglob("*") if path.is_file()),
        key=lambda path: str(path).casefold(),
    )


def _grep_with_python(
    guard: WorkspacePathGuard,
    pattern: str,
    target: Path,
    glob_pattern: str | None,
    max_results: int,
) -> str:
    try:
        expression = re.compile(pattern)
    except re.error as error:
        raise BuiltinToolError(f"Invalid grep pattern: {error.msg}") from error

    results: list[str] = []
    for candidate in _python_grep_files(target):
        resolved = guard.resolve(candidate, must_exist=True)
        relative = (
            resolved.name if target.is_file() else str(resolved.relative_to(target))
        )
        if glob_pattern is not None and not Path(relative).match(glob_pattern):
            continue
        try:
            lines = resolved.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(lines, start=1):
            if expression.search(line) is not None:
                results.append(f"{relative}:{line_number}:{line}")
                if len(results) > max_results:
                    return _result_lines(results, max_results=max_results)
    return _result_lines(results, max_results=max_results)


def _grep(
    guard: WorkspacePathGuard,
    pattern: str,
    path: str = ".",
    glob: str | None = None,
    max_results: int = 100,
) -> str:
    target = guard.resolve(path, must_exist=True)
    if not target.is_file() and not target.is_dir():
        raise BuiltinToolError(f"Path is not a file or directory: {path}")
    executable = shutil.which("rg")
    if executable is not None:
        return _grep_with_rg(executable, pattern, target, glob, max_results)
    return _grep_with_python(guard, pattern, target, glob, max_results)


def _atomic_write_text(path: Path, content: str, *, requested_path: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not path.is_file():
            raise BuiltinToolError(f"Path is not a regular file: {requested_path}")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".moiryx-",
            suffix=".tmp",
        )
    except BuiltinToolError:
        raise
    except OSError as error:
        raise BuiltinToolError(
            f"Could not prepare file '{requested_path}' ({type(error).__name__})"
        ) from error

    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(
            descriptor,
            mode="w",
            encoding="utf-8",
            newline="",
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    except (OSError, UnicodeError) as error:
        raise BuiltinToolError(
            f"Could not write file '{requested_path}' ({type(error).__name__})"
        ) from error
    finally:
        with suppress(OSError):
            temporary_path.unlink(missing_ok=True)


def _write_file(guard: WorkspacePathGuard, path: str, content: str) -> str:
    resolved = guard.resolve(path, must_exist=False)
    _atomic_write_text(resolved, content, requested_path=path)
    return f"Wrote {len(content)} character(s) to {guard.display(resolved)}"


def _edit_file(
    guard: WorkspacePathGuard,
    path: str,
    old_text: str,
    new_text: str,
) -> str:
    resolved = guard.resolve(path, must_exist=True)
    content = _read_utf8(resolved, requested_path=path)
    matches = content.count(old_text)
    if matches != 1:
        raise BuiltinToolError(
            f"Edit requires exactly one match; found {matches}. File was not changed"
        )
    updated = content.replace(old_text, new_text, 1)
    _atomic_write_text(resolved, updated, requested_path=path)
    return f"Edited {guard.display(resolved)}"


_FilesystemSpec = tuple[type[BaseModel], str, Callable[..., Any]]

_FILESYSTEM_SPECS: dict[str, _FilesystemSpec] = {
    "read_file": (
        _ReadFileInput,
        "Read a UTF-8 file, optionally using an inclusive one-based line range.",
        _read_file,
    ),
    "list_files": (
        _ListFilesInput,
        "List immediate files and directories in deterministic order.",
        _list_files,
    ),
    "glob_files": (
        _GlobFilesInput,
        "Find files beneath a directory using a relative glob pattern.",
        _glob_files,
    ),
    "grep": (
        _GrepInput,
        "Search UTF-8 files with a regular expression and bounded results.",
        _grep,
    ),
    "write_file": (
        _WriteFileInput,
        "Atomically write a UTF-8 file, creating parent directories.",
        _write_file,
    ),
    "edit_file": (
        _EditFileInput,
        "Atomically replace text that occurs exactly once in a UTF-8 file.",
        _edit_file,
    ),
}


def build_filesystem_tool(
    name: str,
    guard: WorkspacePathGuard,
) -> ToolDefinition | None:
    """Bind one filesystem definition to an immutable workspace guard."""
    spec = _FILESYSTEM_SPECS.get(name)
    if spec is None:
        return None
    input_model, description, function = spec
    return ToolDefinition(
        name=name,
        description=description,
        function=partial(function, guard),
        input_model=input_model,
        return_adapter=TypeAdapter(str),
    )


__all__ = ["build_filesystem_tool"]
