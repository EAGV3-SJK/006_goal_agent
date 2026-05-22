"""Entry point: run the Session 6 agent against one of the five target queries.

Usage:
    uv run python run_agent.py A
    uv run python run_agent.py B
    uv run python run_agent.py C1   # Query C run 1 (stores mom's birthday)
    uv run python run_agent.py C2   # Query C run 2 (recalls mom's birthday)
    uv run python run_agent.py D
    uv run python run_agent.py "Your custom query here"
"""
import asyncio
import sys

QUERIES = {
    "A": (
        "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his "
        "birth date, death date, and three key contributions to information theory."
    ),
    "B": (
        "Find 3 family-friendly things to do in Tokyo this weekend. "
        "Check Saturday's weather forecast there and tell me which one is most appropriate."
    ),
    "C1": (
        "My mom's birthday is 15 May 2026. Remember that and give me "
        "a calendar reminder for two weeks before and on the day."
    ),
    "C2": "When is mom's birthday?",
    "D": (
        "Search for 'Python asyncio best practices', read the top 3 results, "
        "and give me a short numbered list of the advice they agree on."
    ),
}


async def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "A"
    query = QUERIES.get(key, key)

    print(f"\n{'='*70}")
    print(f"QUERY [{key}]: {query}")
    print(f"{'='*70}")

    from agent6 import run_agent
    return await run_agent(query)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
