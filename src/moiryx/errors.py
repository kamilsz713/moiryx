"""Moiryx exception taxonomy and shared diagnostic context."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from types import MappingProxyType

_ContextValue = str | int


class MoiryxError(Exception):
    """Base class for errors raised by Moiryx."""

    def __init__(
        self,
        message: str,
        *,
        agent_name: str | None = None,
        model_alias: str | None = None,
        provider_name: str | None = None,
        model_id: str | None = None,
        run_id: str | None = None,
        tool_name: str | None = None,
        attempts: int | None = None,
        limit: int | None = None,
    ) -> None:
        context = {
            key: value
            for key, value in (
                ("agent", agent_name),
                ("model", model_alias),
                ("provider", provider_name),
                ("model_id", model_id),
                ("run", run_id),
                ("tool", tool_name),
                ("attempts", attempts),
                ("limit", limit),
            )
            if value is not None
        }
        self.message = message
        self.context: Mapping[str, _ContextValue] = MappingProxyType(context)

        suffix = ", ".join(f"{key}={value}" for key, value in context.items())
        rendered = f"{message} [{suffix}]" if suffix else message
        super().__init__(rendered)


class ConfigurationError(MoiryxError):
    """Global configuration is missing or invalid."""


class AgentDefinitionError(MoiryxError):
    """An agent definition cannot be loaded or validated."""


class ProviderNotFoundError(MoiryxError):
    """A configured provider cannot be resolved."""


class UnknownModelError(MoiryxError):
    """A logical model alias is unknown."""


class ProviderCapabilityError(MoiryxError):
    """A provider cannot satisfy an agent's required capabilities."""


class ProviderRequestError(MoiryxError):
    """A provider request failed with explicit retry classification."""

    _RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool | None = None,
        agent_name: str | None = None,
        model_alias: str | None = None,
        provider_name: str | None = None,
        model_id: str | None = None,
        run_id: str | None = None,
        attempts: int | None = None,
        limit: int | None = None,
    ) -> None:
        if status_code is not None and (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 100 <= status_code <= 599
        ):
            raise ValueError("status_code must be an HTTP status from 100 to 599")
        self.status_code = status_code
        self.retryable = (
            status_code in self._RETRYABLE_STATUS_CODES
            if retryable is None
            else retryable
        )
        super().__init__(
            message,
            agent_name=agent_name,
            model_alias=model_alias,
            provider_name=provider_name,
            model_id=model_id,
            run_id=run_id,
            attempts=attempts,
            limit=limit,
        )


class UnknownToolError(MoiryxError):
    """A requested tool is not registered."""


class DuplicateToolError(MoiryxError):
    """A tool name is already registered."""


class ToolDefinitionError(MoiryxError):
    """A Python function cannot be represented as a Moiryx tool."""


class ToolValidationError(MoiryxError):
    """Tool-call arguments do not satisfy the tool input schema."""


class ToolExecutionError(MoiryxError):
    """A tool function failed or returned an unserializable value."""


class BuiltinToolError(MoiryxError):
    """A built-in tool rejected a safe, user-correctable operation."""


class ToolTimeoutError(MoiryxError):
    """A tool function exceeded its configured execution timeout."""


class ToolCallParseError(MoiryxError):
    """Tool-call arguments cannot be parsed."""


class ToolCallRepairError(MoiryxError):
    """The tool-call repair budget was exhausted."""

    def __init__(
        self,
        message: str,
        *,
        raw_arguments: object | None = None,
        error_summary: str | None = None,
        agent_name: str | None = None,
        model_alias: str | None = None,
        provider_name: str | None = None,
        model_id: str | None = None,
        run_id: str | None = None,
        tool_name: str | None = None,
        attempts: int | None = None,
        limit: int | None = None,
    ) -> None:
        self.raw_arguments = deepcopy(raw_arguments)
        self.error_summary = error_summary
        super().__init__(
            message,
            agent_name=agent_name,
            model_alias=model_alias,
            provider_name=provider_name,
            model_id=model_id,
            run_id=run_id,
            tool_name=tool_name,
            attempts=attempts,
            limit=limit,
        )


class StructuredOutputError(MoiryxError):
    """A structured result cannot be validated or repaired."""


class AgentProtocolError(MoiryxError):
    """A provider response violates the agent protocol."""


class MaxStepsExceeded(MoiryxError):
    """An agent did not finish within its configured step limit."""


__all__ = [
    "AgentDefinitionError",
    "AgentProtocolError",
    "BuiltinToolError",
    "ConfigurationError",
    "DuplicateToolError",
    "MaxStepsExceeded",
    "MoiryxError",
    "ProviderCapabilityError",
    "ProviderNotFoundError",
    "ProviderRequestError",
    "StructuredOutputError",
    "ToolCallParseError",
    "ToolCallRepairError",
    "ToolDefinitionError",
    "ToolExecutionError",
    "ToolTimeoutError",
    "ToolValidationError",
    "UnknownModelError",
    "UnknownToolError",
]
