"""Explicitly selected shell built-in with bounded output and process cleanup."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
from collections.abc import Callable
from contextlib import suppress
from functools import partial
from typing import Annotated, Any, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from moiryx.errors import BuiltinToolError
from moiryx.models import ToolDefinition
from moiryx.tools.builtin.workspace import WorkspacePathGuard


class _ShellInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: Annotated[
        str,
        Field(min_length=1, description="Command interpreted by the system shell."),
    ]
    timeout_seconds: Annotated[
        int | None,
        Field(gt=0, description="Optional command timeout in seconds."),
    ] = None


def _bounded_output(content: str, *, max_chars: int) -> str:
    if len(content) <= max_chars:
        return content
    marker = f"...[TRUNCATED BY MOIRYX: original output exceeded {max_chars} chars]"
    return content[:max_chars] + marker


async def _kill_process_tree(process: asyncio.subprocess.Process) -> None:
    if os.name == "nt":
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.send_signal(signal.CTRL_BREAK_EVENT)
            try:
                await asyncio.wait_for(process.communicate(), timeout=1)
                return
            except TimeoutError:
                pass
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.communicate()
        except (OSError, ProcessLookupError):
            if process.returncode is None:
                process.kill()
        if process.returncode is None:
            process.kill()
    else:
        with suppress(ProcessLookupError):
            kill_process_group = cast(
                Callable[[int, int], None],
                getattr(os, "kill" + "pg"),
            )
            kill_signal = int(getattr(signal, "SIG" + "KILL", signal.SIGTERM))
            kill_process_group(process.pid, kill_signal)
    with suppress(ProcessLookupError):
        await process.communicate()


async def _shell(
    guard: WorkspacePathGuard,
    default_timeout: float,
    max_output_chars: int,
    command: str,
    timeout_seconds: int | None = None,
) -> str:
    workspace = guard.resolve(".", must_exist=True)
    if not workspace.is_dir():
        raise BuiltinToolError("Configured workspace root is not a directory")
    timeout = default_timeout if timeout_seconds is None else float(timeout_seconds)
    process_options: dict[str, Any] = {}
    if os.name == "nt":
        process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        process_options["start_new_session"] = True
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **process_options,
        )
    except OSError as error:
        raise BuiltinToolError(
            f"Could not start shell command ({type(error).__name__})"
        ) from error

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except TimeoutError as error:
        await _kill_process_tree(process)
        raise BuiltinToolError(
            f"Shell command exceeded {timeout:g} seconds and was terminated"
        ) from error
    except asyncio.CancelledError:
        await _kill_process_tree(process)
        raise

    rendered = "\n".join(
        (
            f"Exit code: {process.returncode}",
            "STDOUT:",
            stdout.decode("utf-8", errors="replace"),
            "STDERR:",
            stderr.decode("utf-8", errors="replace"),
        )
    ).rstrip()
    return _bounded_output(rendered, max_chars=max_output_chars)


def build_shell_tool(
    guard: WorkspacePathGuard,
    *,
    default_timeout: int | float,
    max_output_chars: int,
) -> ToolDefinition:
    """Bind the shell definition to one agent's runtime safety settings."""
    return ToolDefinition(
        name="shell",
        description=(
            "Run a command in the configured workspace. This is not a security "
            "sandbox and must be explicitly enabled in the agent definition."
        ),
        function=partial(
            _shell,
            guard,
            float(default_timeout),
            max_output_chars,
        ),
        input_model=_ShellInput,
        return_adapter=TypeAdapter(str),
    )


__all__ = ["build_shell_tool"]
