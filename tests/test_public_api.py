"""Smoke tests for the initial package contract."""

import inspect

import moiryx


def test_public_api_exports_only_agent_and_tool() -> None:
    namespace: dict[str, object] = {}

    exec("from moiryx import *", namespace)

    exported = {name for name in namespace if not name.startswith("__")}
    assert moiryx.__all__ == ["Agent", "tool"]
    assert exported == {"Agent", "tool"}


def test_agent_preserves_constructor_contract() -> None:
    assert list(inspect.signature(moiryx.Agent).parameters) == ["agent_file"]


def test_tool_placeholder_keeps_function_directly_callable() -> None:
    @moiryx.tool
    def increment(value: int) -> int:
        return value + 1

    assert increment(1) == 2
