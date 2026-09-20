"""Minimal public-API smoke test intended for an installed wheel."""

from moiryx import Agent, tool


@tool
def echo(value: str) -> str:
    """Return a value unchanged."""
    return value


def main() -> None:
    """Verify the two intentionally public entry points."""
    assert Agent.__name__ == "Agent"
    assert echo("moiryx-wheel-ok") == "moiryx-wheel-ok"
    print("moiryx wheel smoke: ok")


if __name__ == "__main__":
    main()
