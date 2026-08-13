from __future__ import annotations

import asyncio
import os

from scp.llm_gateway.client import get_gateway


async def main() -> None:
    gateway = get_gateway()
    print(f"gateway={type(gateway).__name__}")
    for name in ("ollama_default", "ollama_why", "ollama_judge", "ollama_fast"):
        provider = getattr(gateway, name, None)
        print(
            f"{name}|enabled={getattr(provider, 'enabled', None)}|"
            f"model={getattr(provider, 'model', None)}|"
            f"host={getattr(provider, 'host', None)}|"
            f"timeout={getattr(provider, 'timeout', None)}"
        )
    answer, provider_name = await gateway.chat(
        "What is the capital of France?",
        context="",
        system_prompt="Answer briefly and factually.",
        task="default",
    )
    print(f"chat|provider={provider_name}|answer={answer!r}")
    print(f"stats={gateway.stats()}")


if __name__ == "__main__":
    asyncio.run(main())
