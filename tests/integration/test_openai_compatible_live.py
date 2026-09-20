"""Explicitly opt-in smoke test for a local OpenAI-compatible endpoint."""

from __future__ import annotations

import os

import pytest

from moiryx.config import OpenAICompatibleProviderConfig
from moiryx.messages import UserMessage
from moiryx.models import GenerationOptions, ModelRequest
from moiryx.providers import OpenAICompatibleProvider

pytestmark = pytest.mark.integration

_LIVE_URL = os.getenv("MOIRYX_OPENAI_COMPATIBLE_LIVE_URL")
_LIVE_MODEL = os.getenv("MOIRYX_OPENAI_COMPATIBLE_LIVE_MODEL")


@pytest.mark.skipif(
    not (_LIVE_URL and _LIVE_MODEL),
    reason=(
        "set MOIRYX_OPENAI_COMPATIBLE_LIVE_URL and "
        "MOIRYX_OPENAI_COMPATIBLE_LIVE_MODEL to opt in"
    ),
)
@pytest.mark.asyncio
async def test_local_openai_compatible_text_smoke() -> None:
    config_payload: dict[str, object] = {
        "type": "openai_compatible",
        "base_url": _LIVE_URL,
        "timeout_seconds": 30,
    }
    api_key = os.getenv("MOIRYX_OPENAI_COMPATIBLE_LIVE_API_KEY")
    if api_key:
        config_payload["api_key"] = api_key
    provider = OpenAICompatibleProvider(
        OpenAICompatibleProviderConfig.model_validate(config_payload)
    )

    try:
        response = await provider.complete(
            ModelRequest(
                model=_LIVE_MODEL or "",
                messages=[UserMessage("Reply with exactly: moiryx-live-ok")],
                generation=GenerationOptions(temperature=0, max_tokens=16),
            )
        )
    finally:
        await provider.close()

    assert response.content is not None
    assert "moiryx-live-ok" in response.content.casefold()
