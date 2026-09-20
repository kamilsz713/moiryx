"""Tests for workspace-scoped filesystem and shell built-in tools."""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from moiryx.config import RuntimeConfig
from moiryx.errors import BuiltinToolError, ToolExecutionError
from moiryx.models import ToolDefinition
from moiryx.tools import (
    BUILTIN_TOOL_NAMES,
    ToolExecutor,
    WorkspacePathError,
    WorkspacePathGuard,
    build_builtin_tool,
    build_tool_message,
)
from moiryx.tools.builtin import filesystem


def _runtime(
    root: Path,
    *,
    allow_outside: bool = False,
    timeout: int | float = 5,
    max_output_chars: int = 50_000,
) -> RuntimeConfig:
    return RuntimeConfig(
        workspace_root=root,
        allow_paths_outside_workspace=allow_outside,
        tool_timeout_seconds=timeout,
        max_tool_output_chars=max_output_chars,
    )


def _definition(
    name: str,
    root: Path,
    *,
    allow_outside: bool = False,
    timeout: int | float = 5,
    max_output_chars: int = 50_000,
) -> ToolDefinition:
    definition = build_builtin_tool(
        name,
        _runtime(
            root,
            allow_outside=allow_outside,
            timeout=timeout,
            max_output_chars=max_output_chars,
        ),
    )
    assert definition is not None
    return definition


async def _invoke(
    definition: ToolDefinition,
    arguments: dict[str, object],
    *,
    executor_timeout: int | float = 10,
) -> Any:
    return await ToolExecutor(executor_timeout).execute(definition, arguments)


def _python_command(source: str) -> str:
    arguments = [sys.executable, "-c", source]
    return (
        subprocess.list2cmdline(arguments) if os.name == "nt" else shlex.join(arguments)
    )


def test_builtin_catalog_is_complete_and_definitions_are_configured(
    tmp_path: Path,
) -> None:
    expected = {
        "read_file",
        "list_files",
        "glob_files",
        "grep",
        "write_file",
        "edit_file",
        "shell",
    }

    assert expected == BUILTIN_TOOL_NAMES
    for name in expected:
        definition = _definition(name, tmp_path)
        assert definition.name == name
        assert definition.schema.parameters["additionalProperties"] is False
        assert definition.description
    assert build_builtin_tool("custom", _runtime(tmp_path)) is None


def test_workspace_guard_blocks_traversal_and_allows_explicit_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    guard = WorkspacePathGuard(root)

    assert guard.resolve("inside.txt") == (root / "inside.txt").resolve()
    with pytest.raises(WorkspacePathError, match="outside"):
        guard.resolve("../outside.txt", must_exist=True)
    with pytest.raises(WorkspacePathError, match="outside"):
        guard.resolve(outside, must_exist=True)

    permissive = WorkspacePathGuard(root, allow_outside=True)
    assert permissive.resolve(outside, must_exist=True) == outside.resolve()


def test_workspace_guard_blocks_directory_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = root / "link"
    junction = False
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        if os.name != "nt":
            pytest.skip(f"directory symlinks are unavailable: {type(error).__name__}")
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True,
            check=False,
        )
        if created.returncode:
            pytest.skip("directory symlinks and junctions are unavailable")
        junction = True

    try:
        with pytest.raises(WorkspacePathError, match="outside"):
            WorkspacePathGuard(root).resolve("link/secret.txt", must_exist=True)
    finally:
        if junction:
            os.rmdir(link)
        else:
            link.unlink()


@pytest.mark.asyncio
async def test_read_file_supports_full_content_and_inclusive_ranges(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.txt"
    source.write_bytes(b"one\r\ntwo\nthree")
    definition = _definition("read_file", tmp_path)

    assert await _invoke(definition, {"path": "sample.txt"}) == "one\r\ntwo\nthree"
    assert (
        await _invoke(
            definition,
            {"path": "sample.txt", "start_line": 2, "end_line": 3},
        )
        == "two\nthree"
    )
    assert (
        await _invoke(
            definition,
            {"path": "sample.txt", "start_line": 2},
        )
        == "two\nthree"
    )


@pytest.mark.asyncio
async def test_read_file_errors_are_safe_and_output_uses_global_limit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("first\nsecond\n", encoding="utf-8")
    invalid_utf8 = tmp_path / "binary.dat"
    invalid_utf8.write_bytes(b"\xff\xfe")
    definition = _definition("read_file", tmp_path)

    with pytest.raises(ToolExecutionError, match="file has 2 line"):
        await _invoke(
            definition,
            {"path": "sample.txt", "start_line": 3, "end_line": 4},
        )
    with pytest.raises(ToolExecutionError, match="not valid UTF-8"):
        await _invoke(definition, {"path": "binary.dat"})
    with pytest.raises(ToolExecutionError, match="Path does not exist"):
        await _invoke(definition, {"path": "missing.txt"})

    result = await _invoke(definition, {"path": "sample.txt"})
    message = build_tool_message(
        "read",
        "read_file",
        result,
        return_adapter=definition.return_adapter,
        max_chars=5,
    )
    assert message.content.startswith("first")
    assert "TRUNCATED BY MOIRYX" in message.content


@pytest.mark.asyncio
async def test_list_and_glob_are_sorted_bounded_and_workspace_scoped(
    tmp_path: Path,
) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.py").write_text("a", encoding="utf-8")
    (tmp_path / "nested" / "c.py").write_text("c", encoding="utf-8")

    listed = await _invoke(
        _definition("list_files", tmp_path),
        {"max_results": 2},
    )
    globbed = await _invoke(
        _definition("glob_files", tmp_path),
        {"pattern": "**/*.py", "max_results": 1},
    )

    assert listed.splitlines()[:2] == ["a.py", "b.txt"]
    assert "more than 2 results" in listed
    assert globbed.splitlines()[0] == "a.py"
    assert "more than 1 results" in globbed
    with pytest.raises(ToolExecutionError, match="parent traversal"):
        await _invoke(
            _definition("glob_files", tmp_path),
            {"pattern": "../*.txt"},
        )


@pytest.mark.asyncio
async def test_python_grep_fallback_filters_glob_and_limits_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "a.py").write_text("needle one\nneedle two\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("needle ignored\n", encoding="utf-8")
    monkeypatch.setattr(filesystem.shutil, "which", lambda name: None)

    result = await _invoke(
        _definition("grep", tmp_path),
        {"pattern": "needle", "glob": "*.py", "max_results": 1},
    )

    assert result.splitlines()[0] == "a.py:1:needle one"
    assert "more than 1 results" in result
    with pytest.raises(ToolExecutionError, match="Invalid grep pattern"):
        await _invoke(
            _definition("grep", tmp_path),
            {"pattern": "["},
        )


@pytest.mark.asyncio
async def test_ripgrep_uses_argument_list_and_never_shell_true(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        arguments: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        captured["arguments"] = arguments
        captured.update(kwargs)
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout="a.py:1:needle\n",
            stderr="",
        )

    monkeypatch.setattr(filesystem.shutil, "which", lambda name: "rg-test")
    monkeypatch.setattr(filesystem.subprocess, "run", fake_run)

    result = await _invoke(
        _definition("grep", tmp_path),
        {"pattern": "needle", "glob": "*.py"},
    )

    arguments = captured["arguments"]
    assert isinstance(arguments, list)
    assert arguments[0] == "rg-test"
    assert arguments[-3:] == ["--", "needle", "."]
    assert captured["shell"] is False
    assert result == "a.py:1:needle"


@pytest.mark.asyncio
async def test_write_file_creates_parents_and_blocks_outside_before_mutation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    definition = _definition("write_file", root)

    result = await _invoke(
        definition,
        {"path": "nested/result.txt", "content": "created"},
    )

    assert (root / "nested" / "result.txt").read_text(encoding="utf-8") == "created"
    assert result == "Wrote 7 character(s) to nested/result.txt"
    outside = tmp_path / "outside" / "blocked.txt"
    with pytest.raises(ToolExecutionError, match="outside"):
        await _invoke(
            definition,
            {"path": str(outside), "content": "must not exist"},
        )
    assert not outside.exists()
    assert not outside.parent.exists()


@pytest.mark.asyncio
async def test_explicit_outside_policy_allows_write(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    definition = _definition("write_file", root, allow_outside=True)

    await _invoke(
        definition,
        {"path": str(outside), "content": "allowed"},
    )

    assert outside.read_text(encoding="utf-8") == "allowed"


@pytest.mark.asyncio
async def test_edit_requires_exactly_one_match_without_partial_mutation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.txt"
    definition = _definition("edit_file", tmp_path)

    target.write_text("alpha beta", encoding="utf-8")
    with pytest.raises(ToolExecutionError, match="found 0"):
        await _invoke(
            definition,
            {"path": "target.txt", "old_text": "missing", "new_text": "new"},
        )
    assert target.read_text(encoding="utf-8") == "alpha beta"

    target.write_text("same same", encoding="utf-8")
    with pytest.raises(ToolExecutionError, match="found 2"):
        await _invoke(
            definition,
            {"path": "target.txt", "old_text": "same", "new_text": "changed"},
        )
    assert target.read_text(encoding="utf-8") == "same same"

    result = await _invoke(
        definition,
        {"path": "target.txt", "old_text": "same same", "new_text": "changed"},
    )
    assert target.read_text(encoding="utf-8") == "changed"
    assert result == "Edited target.txt"


@pytest.mark.asyncio
async def test_edit_replace_failure_keeps_original_and_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target.txt"
    target.write_text("before", encoding="utf-8")
    definition = _definition("edit_file", tmp_path)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(filesystem.os, "replace", fail_replace)

    with pytest.raises(ToolExecutionError, match="Could not write file"):
        await _invoke(
            definition,
            {"path": "target.txt", "old_text": "before", "new_text": "after"},
        )

    assert target.read_text(encoding="utf-8") == "before"
    assert list(tmp_path.glob(".moiryx-*.tmp")) == []


@pytest.mark.asyncio
async def test_shell_uses_workspace_reports_streams_and_limits_output(
    tmp_path: Path,
) -> None:
    source = (
        "import os,sys; print(os.getcwd()); print('x' * 200); "
        "print('problem', file=sys.stderr); raise SystemExit(3)"
    )
    definition = _definition("shell", tmp_path, max_output_chars=140)

    result = await _invoke(
        definition,
        {"command": _python_command(source)},
    )

    assert "Exit code: 3" in result
    assert str(tmp_path.resolve()) in result
    assert "STDOUT:" in result
    assert "TRUNCATED BY MOIRYX" in result
    assert len(result) < 230


@pytest.mark.asyncio
async def test_shell_timeout_terminates_child_process(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-appear.txt"
    source = (
        "import pathlib,time; time.sleep(1); "
        f"pathlib.Path({str(marker)!r}).write_text('late')"
    )
    definition = _definition("shell", tmp_path, timeout=0.1)

    with pytest.raises(ToolExecutionError, match="was terminated"):
        await _invoke(
            definition,
            {"command": _python_command(source)},
            executor_timeout=3,
        )

    await asyncio.sleep(1.1)
    assert not marker.exists()


def test_workspace_path_error_is_a_safe_builtin_error(tmp_path: Path) -> None:
    error = WorkspacePathError("Path is outside the configured workspace")

    assert isinstance(error, BuiltinToolError)
    assert "outside" in str(error)
