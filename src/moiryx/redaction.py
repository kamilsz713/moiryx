"""Central, recursive secret redaction for configuration and diagnostics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import BaseModel, SecretStr

REDACTED = "**********"

_SENSITIVE_NAMES = {
    "api-key",
    "apikey",
    "authorization",
    "client-secret",
    "credentials",
    "password",
    "private-key",
    "proxy-authorization",
    "refresh-token",
    "service-account",
    "x-api-key",
}


def _normalized_key(key: object) -> str:
    return str(key).strip().casefold().replace("_", "-")


def is_sensitive_key(key: object) -> bool:
    """Return whether a field name conventionally contains a secret."""
    normalized = _normalized_key(key)
    return normalized in _SENSITIVE_NAMES or normalized.endswith(
        ("-key", "-secret", "-token")
    )


def redact_text(text: str, *, secrets: Iterable[str] = ()) -> str:
    """Replace each known non-empty secret embedded in text."""
    redacted = text
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        redacted = redacted.replace(secret, REDACTED)
    return redacted


def redact(
    value: object,
    *,
    secrets: Iterable[str] = (),
    key: object | None = None,
) -> object:
    """Recursively redact sensitive keys, SecretStr values, and known secrets."""
    secret_values = tuple(secrets)
    if key is not None and is_sensitive_key(key):
        return REDACTED
    if isinstance(value, SecretStr):
        return REDACTED
    if isinstance(value, BaseModel):
        return redact(value.model_dump(), secrets=secret_values)
    if isinstance(value, Mapping):
        return {
            item_key: redact(item, secrets=secret_values, key=item_key)
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, secrets=secret_values) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item, secrets=secret_values) for item in value)
    if isinstance(value, str):
        return redact_text(value, secrets=secret_values)
    return value


def collect_secret_values(value: object) -> tuple[str, ...]:
    """Collect configured secrets without retaining duplicate values."""
    found: set[str] = set()

    def visit(item: object, *, sensitive: bool = False) -> None:
        if isinstance(item, SecretStr):
            secret = item.get_secret_value()
            if secret:
                found.add(secret)
            return
        if isinstance(item, BaseModel):
            visit(item.model_dump(), sensitive=sensitive)
            return
        if isinstance(item, Mapping):
            for item_key, child in item.items():
                visit(child, sensitive=sensitive or is_sensitive_key(item_key))
            return
        if isinstance(item, (list, tuple)):
            for child in item:
                visit(child, sensitive=sensitive)
            return
        if sensitive and isinstance(item, str) and item:
            found.add(item)

    visit(value)
    return tuple(sorted(found, key=len, reverse=True))


__all__ = [
    "REDACTED",
    "collect_secret_values",
    "is_sensitive_key",
    "redact",
    "redact_text",
]
