import asyncio

from config import get_llm_config
from agent import AsyncAIAgent


async def main():
    config = get_llm_config()
    print(f"Backend: {config['backend']}")
    print(f"Base URL: {config['base_url']}")
    print(f"Model: {config['model']}")

    agent = AsyncAIAgent()
    response = await agent.get_ai_response("Reply with one short sentence: Scout backend is working.")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
