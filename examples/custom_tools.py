"""Example custom tools imported through ``tool_modules``."""

from moiryx import tool


@tool
def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())
