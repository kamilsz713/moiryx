"""Standard logging and per-run JSONL event tracing."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from threading import Lock

from pydantic import BaseModel

from moiryx.config import LoggingConfig
from moiryx.redaction import redact

LOGGER_NAME = "moiryx.run"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _jsonable(model_dump(mode="json"))
    return {"type": type(value).__name__}


class RunObserver:
    """Emit redacted run events to logging and an optional isolated trace file."""

    __slots__ = (
        "_include_raw_response",
        "_level",
        "_lock",
        "_logger",
        "_secrets",
        "_trace_dir",
    )

    def __init__(
        self,
        config: LoggingConfig | None = None,
        *,
        secrets: tuple[str, ...] = (),
        logger: logging.Logger | None = None,
    ) -> None:
        settings = config or LoggingConfig()
        self._level = getattr(logging, settings.level)
        self._trace_dir = settings.trace_dir
        self._include_raw_response = settings.include_raw_response
        self._secrets = secrets
        self._logger = logger or logging.getLogger(LOGGER_NAME)
        self._lock = Lock()

    @property
    def include_raw_response(self) -> bool:
        return self._include_raw_response

    def emit(
        self,
        event: str,
        *,
        run_id: str,
        level: int,
        **fields: object,
    ) -> None:
        """Emit one structured, redacted event."""
        record: dict[str, object] = {
            "timestamp": _timestamp(),
            "run_id": run_id,
            "event": event,
            "level": logging.getLevelName(level),
            **{key: _jsonable(value) for key, value in fields.items()},
        }
        safe = redact(record, secrets=self._secrets)
        if not isinstance(safe, Mapping):
            raise TypeError("redacted event must remain a mapping")
        serialized = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))

        if level >= self._level:
            self._logger.log(level, serialized)
        if self._trace_dir is None:
            return
        trace_path = self._trace_dir / run_id / "events.jsonl"
        with self._lock:
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            with trace_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(serialized)
                stream.write("\n")


__all__ = ["LOGGER_NAME", "RunObserver"]
