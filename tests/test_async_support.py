"""Smoke test for the configured asynchronous pytest support."""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_async_test_support_is_available() -> None:
    await asyncio.sleep(0)
