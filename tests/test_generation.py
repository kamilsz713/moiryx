"""Tests for generation option validation and precedence."""

import pytest

from moiryx.errors import ConfigurationError
from moiryx.generation import merge_generation_options
from moiryx.models import GenerationOptions


def test_generation_precedence_is_runtime_then_model_then_agent() -> None:
    merged = merge_generation_options(
        runtime=GenerationOptions(
            temperature=0.8,
            max_tokens=1000,
            top_p=0.95,
            seed=1,
        ),
        model={"temperature": 0.4, "max_tokens": 500},
        agent={"temperature": 0.2, "seed": 7},
    )

    assert merged == GenerationOptions(
        temperature=0.2,
        max_tokens=500,
        top_p=0.95,
        seed=7,
    )


def test_none_values_do_not_erase_lower_priority_defaults() -> None:
    merged = merge_generation_options(
        runtime={"temperature": 0.7, "max_tokens": 100},
        model={"temperature": None},
        agent=None,
    )

    assert merged.temperature == 0.7
    assert merged.max_tokens == 100


def test_unknown_generation_option_is_not_ignored() -> None:
    with pytest.raises(ConfigurationError, match=r"unknown option.*frequency_penalty"):
        merge_generation_options(model={"frequency_penalty": 0.5})


@pytest.mark.parametrize(
    ("settings", "message"),
    (
        ({"temperature": -0.1}, "temperature"),
        ({"temperature": "warm"}, "temperature"),
        ({"max_tokens": 0}, "max_tokens"),
        ({"max_tokens": True}, "max_tokens"),
        ({"top_p": 1.1}, "top_p"),
        ({"seed": 1.5}, "seed"),
    ),
)
def test_invalid_generation_values_are_rejected(
    settings: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        merge_generation_options(agent=settings)
