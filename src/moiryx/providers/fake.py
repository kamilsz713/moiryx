"""Deterministic scripted provider for offline runtime tests."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from copy import deepcopy
from typing import TypeAlias

from moiryx.models import ModelRequest, ModelResponse, ProviderCapabilities

ScriptedItem: TypeAlias = ModelResponse | Exception


class ScriptedFakeProvider:
    """Return responses or raise errors from a fixed FIFO script."""

    __slots__ = (
        "_capabilities",
        "_closed",
        "_script",
        "close_calls",
        "requests",
    )

    def __init__(
        self,
        script: Iterable[ScriptedItem],
        *,
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        items = tuple(script)
        if any(not isinstance(item, (ModelResponse, Exception)) for item in items):
            raise TypeError(
                "script items must be ModelResponse instances or exceptions"
            )
        self._script = deque(items)
        self._capabilities = capabilities or ProviderCapabilities(
            tool_calling=True,
            native_structured_output=True,
            parallel_tool_calls=True,
        )
        self._closed = False
        self.requests: list[ModelRequest] = []
        self.close_calls = 0

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    @property
    def remaining(self) -> int:
        """Return the number of scripted items not consumed yet."""
        return len(self._script)

    @property
    def closed(self) -> bool:
        return self._closed

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Record a request snapshot and consume the next scripted item."""
        if self._closed:
            raise RuntimeError("scripted fake provider is closed")
        self.requests.append(deepcopy(request))
        if not self._script:
            raise AssertionError("scripted fake provider response queue is exhausted")
        item = self._script.popleft()
        if isinstance(item, Exception):
            raise item
        return deepcopy(item)

    async def close(self) -> None:
        """Close idempotently while exposing one observable cleanup count."""
        if self._closed:
            return
        self._closed = True
        self.close_calls += 1


__all__ = ["ScriptedFakeProvider", "ScriptedItem"]
