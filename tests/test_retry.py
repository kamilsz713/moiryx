"""Tests for provider error classification and bounded retry behavior."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from moiryx.errors import ProviderRequestError
from moiryx.models import ModelRequest, ModelResponse
from moiryx.providers import ScriptedFakeProvider
from moiryx.retry import ProviderRetry, is_retryable_provider_error


def _request() -> ModelRequest:
    return ModelRequest(model="vendor/model", messages=[])


async def _complete(
    retry: ProviderRetry,
    provider: ScriptedFakeProvider,
) -> ModelResponse:
    return await retry.complete(
        provider,
        _request(),
        agent_name="reviewer",
        model_alias="strong",
        provider_name="local",
        model_id="vendor/model",
        run_id="run-1",
    )


@pytest.mark.parametrize("status", (429, 500, 502, 503, 504))
def test_selected_http_statuses_are_retryable(status: int) -> None:
    error = ProviderRequestError("transient", status_code=status)

    assert error.retryable is True
    assert is_retryable_provider_error(error) is True


@pytest.mark.parametrize("status", (400, 401, 403, 404, 409, 422, 501, 505))
def test_obvious_client_and_non_transient_server_errors_are_not_retried(
    status: int,
) -> None:
    error = ProviderRequestError("permanent", status_code=status)

    assert error.retryable is False
    assert is_retryable_provider_error(error) is False


def test_transport_timeout_and_reset_are_retryable() -> None:
    assert is_retryable_provider_error(TimeoutError()) is True
    assert is_retryable_provider_error(ConnectionResetError()) is True
    assert is_retryable_provider_error(ConnectionError()) is False


@pytest.mark.asyncio
async def test_transient_errors_use_exponential_backoff_with_jitter() -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    samples: Iterator[float] = iter((0.0, 0.5, 1.0))
    provider = ScriptedFakeProvider(
        [
            TimeoutError("timeout"),
            ConnectionResetError("reset"),
            ProviderRequestError("busy", status_code=503),
            ModelResponse(content="done"),
        ]
    )
    retry = ProviderRetry(
        3,
        base_delay=1,
        max_delay=10,
        jitter_ratio=0.25,
        sleep=record_sleep,
        random_source=lambda: next(samples),
    )

    response = await _complete(retry, provider)

    assert response.content == "done"
    assert delays == [0.75, 2.0, 5.0]
    assert len(provider.requests) == 4


@pytest.mark.asyncio
async def test_non_retryable_error_fails_immediately_with_runtime_context() -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    original = ProviderRequestError("invalid API key", status_code=401)
    provider = ScriptedFakeProvider([original, ModelResponse(content="unused")])
    retry = ProviderRetry(3, sleep=record_sleep)

    with pytest.raises(ProviderRequestError) as captured:
        await _complete(retry, provider)

    error = captured.value
    assert error is not original
    assert error.__cause__ is original
    assert error.status_code == 401
    assert error.retryable is False
    assert error.context == {
        "agent": "reviewer",
        "model": "strong",
        "provider": "local",
        "model_id": "vendor/model",
        "run": "run-1",
        "attempts": 1,
        "limit": 4,
    }
    assert delays == []
    assert provider.remaining == 1


@pytest.mark.asyncio
async def test_retry_exhaustion_reports_total_provider_attempts() -> None:
    async def no_sleep(delay: float) -> None:
        assert delay >= 0

    provider = ScriptedFakeProvider(
        [
            TimeoutError(),
            TimeoutError(),
            TimeoutError(),
            ModelResponse(content="too late"),
        ]
    )
    retry = ProviderRetry(2, sleep=no_sleep, random_source=lambda: 0.5)

    with pytest.raises(ProviderRequestError) as captured:
        await _complete(retry, provider)

    error = captured.value
    assert error.retryable is True
    assert error.context["attempts"] == 3
    assert error.context["limit"] == 3
    assert len(provider.requests) == 3
    assert provider.remaining == 1


@pytest.mark.asyncio
async def test_cancellation_during_backoff_is_not_wrapped() -> None:
    import asyncio

    sleeping = asyncio.Event()
    sleep_cancelled = asyncio.Event()

    async def block_sleep(delay: float) -> None:
        assert delay > 0
        sleeping.set()
        try:
            await asyncio.Event().wait()
        finally:
            sleep_cancelled.set()

    provider = ScriptedFakeProvider([TimeoutError(), ModelResponse(content="unused")])
    retry = ProviderRetry(1, sleep=block_sleep)
    task = asyncio.create_task(_complete(retry, provider))
    await sleeping.wait()

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(sleep_cancelled.wait(), timeout=1)
    assert provider.remaining == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"max_retries": -1}, "max_retries"),
        ({"max_retries": True}, "max_retries"),
        ({"max_retries": 1, "base_delay": 0}, "base_delay"),
        ({"max_retries": 1, "max_delay": 0}, "max_delay"),
        ({"max_retries": 1, "jitter_ratio": 1.1}, "jitter_ratio"),
    ),
)
def test_retry_policy_validates_limits(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ProviderRetry(**kwargs)  # type: ignore[arg-type]
