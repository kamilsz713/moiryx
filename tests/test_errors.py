"""Tests for the internal exception taxonomy."""

from types import MappingProxyType

import pytest

import moiryx
from moiryx import errors

ERROR_TYPES = (
    errors.ConfigurationError,
    errors.AgentDefinitionError,
    errors.ProviderNotFoundError,
    errors.UnknownModelError,
    errors.ProviderCapabilityError,
    errors.ProviderRequestError,
    errors.UnknownToolError,
    errors.DuplicateToolError,
    errors.ToolDefinitionError,
    errors.ToolValidationError,
    errors.ToolExecutionError,
    errors.BuiltinToolError,
    errors.ToolTimeoutError,
    errors.ToolCallParseError,
    errors.ToolCallRepairError,
    errors.StructuredOutputError,
    errors.AgentProtocolError,
    errors.MaxStepsExceeded,
)


@pytest.mark.parametrize("error_type", ERROR_TYPES)
def test_all_specific_errors_share_the_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, errors.MoiryxError)


def test_error_carries_operational_context() -> None:
    error = errors.ToolCallRepairError(
        "Tool call could not be repaired",
        agent_name="reviewer",
        model_alias="reasoning",
        provider_name="router",
        model_id="vendor/model",
        run_id="run-123",
        tool_name="read_file",
        attempts=2,
        limit=2,
    )

    assert isinstance(error.context, MappingProxyType)
    assert error.context["agent"] == "reviewer"
    assert str(error) == (
        "Tool call could not be repaired [agent=reviewer, model=reasoning, "
        "provider=router, model_id=vendor/model, run=run-123, tool=read_file, "
        "attempts=2, limit=2]"
    )


def test_errors_do_not_expand_the_root_public_api() -> None:
    assert moiryx.__all__ == ["Agent", "tool"]
    assert "MoiryxError" not in moiryx.__all__
