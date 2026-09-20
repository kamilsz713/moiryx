"""Validation and precedence rules for shared generation options."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias

from moiryx.errors import ConfigurationError
from moiryx.models import GenerationOptions

GenerationSource: TypeAlias = GenerationOptions | Mapping[str, object] | None

_FIELDS = ("temperature", "max_tokens", "top_p", "seed")
_FIELD_SET = frozenset(_FIELDS)


def _invalid(source_name: str, detail: str) -> ConfigurationError:
    return ConfigurationError(f"Invalid {source_name} generation options: {detail}")


def _validate_number(
    name: str,
    value: object,
    *,
    source_name: str,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(source_name, f"'{name}' must be a number")
    return float(value)


def _overrides(source: GenerationSource, *, source_name: str) -> dict[str, object]:
    if source is None:
        return {}
    if isinstance(source, GenerationOptions):
        values = {name: getattr(source, name) for name in _FIELDS}
    elif isinstance(source, Mapping):
        unknown = sorted(str(name) for name in source if name not in _FIELD_SET)
        if unknown:
            raise _invalid(
                source_name,
                f"unknown option(s): {', '.join(unknown)}",
            )
        values = dict(source)
    else:
        raise _invalid(source_name, "expected a mapping or GenerationOptions")

    validated: dict[str, object] = {}
    for name, value in values.items():
        if value is None:
            continue
        if name == "temperature":
            number = _validate_number(name, value, source_name=source_name)
            if number < 0:
                raise _invalid(source_name, "'temperature' must be non-negative")
            validated[name] = number
        elif name == "top_p":
            number = _validate_number(name, value, source_name=source_name)
            if not 0 < number <= 1:
                raise _invalid(
                    source_name, "'top_p' must be greater than 0 and at most 1"
                )
            validated[name] = number
        elif name == "max_tokens":
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise _invalid(source_name, "'max_tokens' must be a positive integer")
            validated[name] = value
        elif name == "seed":
            if isinstance(value, bool) or not isinstance(value, int):
                raise _invalid(source_name, "'seed' must be an integer")
            validated[name] = value
    return validated


def merge_generation_options(
    runtime: GenerationSource = None,
    model: GenerationSource = None,
    agent: GenerationSource = None,
) -> GenerationOptions:
    """Merge runtime, model, and agent settings from lowest to highest priority."""
    merged: dict[str, object] = {}
    for source_name, source in (
        ("runtime", runtime),
        ("model", model),
        ("agent", agent),
    ):
        merged.update(_overrides(source, source_name=source_name))

    return GenerationOptions(
        temperature=_optional_float(merged.get("temperature")),
        max_tokens=_optional_int(merged.get("max_tokens")),
        top_p=_optional_float(merged.get("top_p")),
        seed=_optional_int(merged.get("seed")),
    )


def _optional_float(value: object | None) -> float | None:
    return value if isinstance(value, float) else None


def _optional_int(value: object | None) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


__all__ = ["GenerationSource", "merge_generation_options"]
