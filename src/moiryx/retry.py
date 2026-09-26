"""Retry classification and bounded exponential backoff for providers."""

from __future__ import annotations

import asyncio
import inspect
import math
import random
from collections.abc import Awaitable, Callable

from moiryx.errors import ProviderRequestError
from moiryx.models import ModelRequest, ModelResponse
from moiryx.providers import ProviderAdapter

SleepFunction = Callable[[float], Awaitable[None]]
RandomFunction = Callable[[], float]
RetryCallback = Callable[[int, float, Exception], Awaitable[None] | None]


def is_retryable_provider_error(error: Exception) -> bool:
    """Return whether a normalized or transport error is transient."""
    if isinstance(error, ProviderRequestError):
        return error.retryable
    return isinstance(error, (TimeoutError, ConnectionResetError))


class ProviderRetry:
    """Complete requests with exponential backoff and bounded jitter."""

    _base_delay: float
    _jitter_ratio: float
    _max_delay: float
    _max_retries: int
    _random: RandomFunction
    _sleep: SleepFunction

    __slots__ = (
        "_base_delay",
        "_jitter_ratio",
        "_max_delay",
        "_max_retries",
        "_random",
        "_sleep",
    )

    def __init__(
        self,
        max_retries: int,
        *,
        base_delay: int | float = 0.5,
        max_delay: int | float = 8.0,
        jitter_ratio: int | float = 0.2,
        sleep: SleepFunction | None = None,
        random_source: RandomFunction | None = None,
    ) -> None:
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or max_retries < 0
        ):
            raise ValueError("max_retries must be a non-negative integer")
        if (
            isinstance(base_delay, bool)
            or not isinstance(base_delay, (int, float))
            or base_delay <= 0
        ):
            raise ValueError("base_delay must be a positive number")
        if (
            isinstance(max_delay, bool)
            or not isinstance(max_delay, (int, float))
            or max_delay <= 0
        ):
            raise ValueError("max_delay must be a positive number")
        if (
            isinstance(jitter_ratio, bool)
            or not isinstance(jitter_ratio, (int, float))
            or not 0 <= jitter_ratio <= 1
        ):
            raise ValueError("jitter_ratio must be between 0 and 1")

        self._max_retries = max_retries
        self._base_delay = float(base_delay)
        self._max_delay = float(max_delay)
        self._jitter_ratio = float(jitter_ratio)
        self._sleep = asyncio.sleep if sleep is None else sleep
        self._random = random.random if random_source is None else random_source

    def delay_for(self, retry_index: int) -> float:
        """Return a capped exponential delay with symmetric jitter."""
        if isinstance(retry_index, bool) or not isinstance(retry_index, int):
            raise ValueError("retry_index must be a non-negative integer")
        if retry_index < 0:
            raise ValueError("retry_index must be a non-negative integer")
        try:
            grown_delay = math.ldexp(self._base_delay, retry_index)
        except OverflowError:
            grown_delay = self._max_delay
        exponential: float = min(self._max_delay, grown_delay)
        sample: float = self._random()
        if not 0 <= sample <= 1:
            raise ValueError("random_source must return a value between 0 and 1")
        jitter = exponential * self._jitter_ratio * ((2 * sample) - 1)
        delay: float = min(self._max_delay, max(0.0, exponential + jitter))
        return delay

    async def complete(
        self,
        provider: ProviderAdapter,
        request: ModelRequest,
        *,
        agent_name: str,
        model_alias: str,
        provider_name: str,
        model_id: str,
        run_id: str,
        on_retry: RetryCallback | None = None,
    ) -> ModelResponse:
        """Complete one logical model step, retrying only transient failures."""
        retries_used = 0
        while True:
            try:
                return await provider.complete(request)
            except (ProviderRequestError, TimeoutError, ConnectionResetError) as error:
                retryable = is_retryable_provider_error(error)
                if not retryable or retries_used >= self._max_retries:
                    raise _contextual_provider_error(
                        error,
                        retryable=retryable,
                        attempts=retries_used + 1,
                        limit=self._max_retries + 1,
                        agent_name=agent_name,
                        model_alias=model_alias,
                        provider_name=provider_name,
                        model_id=model_id,
                        run_id=run_id,
                    ) from error
                delay = self.delay_for(retries_used)
                retries_used += 1
                if on_retry is not None:
                    callback_result = on_retry(retries_used, delay, error)
                    if inspect.isawaitable(callback_result):
                        await callback_result
                await self._sleep(delay)


def _contextual_provider_error(
    error: ProviderRequestError | TimeoutError | ConnectionResetError,
    *,
    retryable: bool,
    attempts: int,
    limit: int,
    agent_name: str,
    model_alias: str,
    provider_name: str,
    model_id: str,
    run_id: str,
) -> ProviderRequestError:
    if isinstance(error, ProviderRequestError):
        message = error.message
        status_code = error.status_code
    else:
        message = f"Provider request failed with {type(error).__name__}"
        status_code = None
    return ProviderRequestError(
        message,
        status_code=status_code,
        retryable=retryable,
        agent_name=agent_name,
        model_alias=model_alias,
        provider_name=provider_name,
        model_id=model_id,
        run_id=run_id,
        attempts=attempts,
        limit=limit,
    )


__all__ = [
    "ProviderRetry",
    "RandomFunction",
    "RetryCallback",
    "SleepFunction",
    "is_retryable_provider_error",
]
