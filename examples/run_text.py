"""Run the basic local text-agent example."""

import asyncio

from moiryx import Agent


async def main() -> None:
    """Ask the configured local model one question."""
    agent = Agent("examples/agents/chat.md")
    answer = await agent("What is the difference between a process and a thread?")
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
