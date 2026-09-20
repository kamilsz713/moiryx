"""Independent correction budget for the structured-result protocol."""

from __future__ import annotations

from moiryx.errors import StructuredOutputError
from moiryx.messages import RepairMessage, ToolMessage

StructuredRepairFeedback = RepairMessage | ToolMessage


class StructuredOutputRepairTracker:
    """Create bounded feedback without consuming provider or tool retries."""

    __slots__ = (
        "_agent_name",
        "_attempts",
        "_limit",
        "_model_alias",
        "_model_id",
        "_provider_name",
        "_run_id",
    )

    def __init__(
        self,
        limit: int,
        *,
        agent_name: str | None = None,
        model_alias: str | None = None,
        provider_name: str | None = None,
        model_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        self._limit = limit
        self._attempts = 0
        self._agent_name = agent_name
        self._model_alias = model_alias
        self._provider_name = provider_name
        self._model_id = model_id
        self._run_id = run_id

    @property
    def attempts(self) -> int:
        return self._attempts

    def feedback_for(
        self,
        message: str,
        *,
        tool_call_id: str | None = None,
    ) -> StructuredRepairFeedback:
        """Consume one correction round, or fail after all rounds were used."""
        if self._attempts >= self._limit:
            raise StructuredOutputError(
                "Structured output repair budget exhausted",
                agent_name=self._agent_name,
                model_alias=self._model_alias,
                provider_name=self._provider_name,
                model_id=self._model_id,
                run_id=self._run_id,
                attempts=self._attempts,
                limit=self._limit,
            )
        self._attempts += 1
        if tool_call_id is not None and tool_call_id.strip():
            return ToolMessage(
                tool_call_id=tool_call_id,
                name="__moiryx_submit_result",
                content=message,
                is_error=True,
            )
        return RepairMessage(content=message)


__all__ = ["StructuredOutputRepairTracker", "StructuredRepairFeedback"]
